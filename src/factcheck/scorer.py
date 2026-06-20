"""
FactCheckScorer — grounded Tier-2 verdict for the Fact-Check track (Mistral Large).

Mirrors the ragebait MediaScorer, but the verdict is open-book:
  - judge_candidates() picks the single most illustrative article from the top-5
    suspicious candidates (1 Large call) — so retrieval + scoring run on one
    article only (winner-only design, keeps Tavily inside the free tier).
  - score() fires THREE sub-scores in parallel (one Large call each):
        factual_accuracy   open-book, grounded on retrieved evidence (FEVER)
        misleading_framing closed-book (Entman)
        missing_context    closed-book (Rogers — paltering)
    The mean is the Irreführungs-Index. Factual Accuracy abstains to NEI when
    evidence is thin and is then EXCLUDED from the mean, so abstention never
    inflates the index.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from src.scoring.llm_client import MistralJSONClient, RANDOM_SEED, TEMPERATURE
from src.scoring.throttle import large_limiter
from src.factcheck.schemas import FactCheckScore, FactCheckResult
from src.factcheck.prompts import (
    FC_ACCURACY_USER,
    FC_CLOSED_USER,
    FACTUAL_ACCURACY_SYSTEM,
    MISLEADING_FRAMING_SYSTEM,
    MISSING_CONTEXT_SYSTEM,
    FC_JUDGE_SYSTEM,
    FC_JUDGE_USER,
)

log = logging.getLogger(__name__)

FC_SCORE_MODEL_ID = "mistral-large-latest"
FC_SCORE_VERSION  = "fc-v1"
MAX_CONTENT_CHARS = 3000
_VALID_LABELS     = {"SUPPORTED", "REFUTED", "NEI"}


def render_evidence(evidence: list[dict]) -> str:
    """Render per-claim evidence bundles into a compact text block for the prompt."""
    if not evidence:
        return "KEINE EXTERNEN BELEGE GEFUNDEN."
    lines: list[str] = []
    for i, b in enumerate(evidence, start=1):
        lines.append(f"BEHAUPTUNG {i}: {b.get('claim', '')}")
        fcs = b.get("fact_checks") or []
        web = b.get("web_evidence") or []
        if fcs:
            lines.append("  Faktencheck-Verdikte:")
            for r in fcs:
                pub = r.get("publisher") or r.get("site") or "?"
                lines.append(f"    - [{r.get('rating', '?')}] {pub}: {r.get('title', '')} ({r.get('url', '')})")
        if web:
            lines.append("  Websuche-Belege:")
            for w in web:
                snippet = (w.get("content", "") or "")[:240]
                lines.append(f"    - ({w.get('score', 0):.2f}) {w.get('title', '')}: {snippet} ({w.get('url', '')})")
        if not fcs and not web:
            lines.append("  (keine Belege gefunden)")
    return "\n".join(lines)


class FactCheckScorer:
    """Usage: FactCheckScorer().score(title, content, claims, evidence) -> FactCheckResult."""

    def __init__(self, api_key: Optional[str] = None, model: str = FC_SCORE_MODEL_ID):
        self._client = MistralJSONClient(model, large_limiter, api_key)

    # ------------------------------------------------------------------
    # Winner selection
    # ------------------------------------------------------------------

    def judge_candidates(self, candidates: list[dict]) -> dict:
        """
        Pick the single best article to fact-check from the suspicious candidates.

        Args:
            candidates: dicts with keys title, fc_pre_score, fc_pre_reasoning,
                        and optional fact_check_hits (list[str] of FCT ratings).

        Returns {"chosen": int (1-indexed), "reasoning": str}.
        """
        lines = []
        for i, c in enumerate(candidates, start=1):
            hits = c.get("fact_check_hits") or []
            hit_str = ("; ".join(hits)[:200] if hits else "keine")
            lines.append(
                f"[Artikel {i}]\n"
                f"Titel: «{c.get('title', '')}»\n"
                f"Verdachts-Score: {c.get('fc_pre_score', 0):.1f}\n"
                f"Verdachts-Begründung: \"{c.get('fc_pre_reasoning', '')}\"\n"
                f"Vorhandene Faktencheck-Treffer: {hit_str}"
            )
        user_msg = FC_JUDGE_USER.format(n=len(candidates), candidates="\n\n".join(lines))
        raw = self._query(FC_JUDGE_SYSTEM, user_msg)
        chosen = int(raw.get("chosen", 1))
        chosen = max(1, min(chosen, len(candidates)))
        return {"chosen": chosen, "reasoning": raw.get("reasoning", "")}

    # ------------------------------------------------------------------
    # Grounded verdict
    # ------------------------------------------------------------------

    def score(
        self,
        title: str,
        content: str,
        claims: list[str],
        evidence: list[dict],
    ) -> FactCheckResult:
        """Fire 3 parallel sub-score calls and aggregate into the Irreführungs-Index."""
        content_trunc = content[:MAX_CONTENT_CHARS]
        evidence_block = render_evidence(evidence)

        tasks = {
            "factual_accuracy":  lambda: self._score_accuracy(title, content_trunc, evidence_block),
            "misleading_framing": lambda: self._score_closed(MISLEADING_FRAMING_SYSTEM, title, content_trunc),
            "missing_context":   lambda: self._score_closed(MISSING_CONTEXT_SYSTEM, title, content_trunc),
        }
        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_map = {executor.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(future_map):
                results[future_map[future]] = future.result()

        acc = results["factual_accuracy"]
        fr  = results["misleading_framing"]
        mc  = results["missing_context"]

        # NEI-aware mean: a NEI accuracy verdict is excluded so abstention never
        # inflates the index. Framing + Missing Context are always counted.
        counted = [fr["score"], mc["score"]]
        accuracy_counted = acc["label"] != "NEI"
        if accuracy_counted:
            counted.append(acc["score"])
        composite = sum(counted) / len(counted)

        reasoning = (
            f"factual_accuracy[{acc['label']}]-{acc['reasoning']} "
            f"misleading_framing-{fr['reasoning']} "
            f"missing_context-{mc['reasoning']}"
        )

        fc = FactCheckScore(
            score=composite,
            factual_accuracy=acc["score"],
            factual_accuracy_label=acc["label"],
            factual_accuracy_reasoning=acc["reasoning"],
            misleading_framing=fr["score"],
            misleading_framing_reasoning=fr["reasoning"],
            missing_context=mc["score"],
            missing_context_reasoning=mc["reasoning"],
            accuracy_counted=accuracy_counted,
            reasoning=reasoning,
        )
        return FactCheckResult(
            fact_check_score=composite,
            fact_check=fc,
            claims=claims,
            evidence=evidence,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_accuracy(self, title: str, content: str, evidence_block: str) -> dict:
        user_msg = FC_ACCURACY_USER.format(title=title, content=content, evidence=evidence_block)
        raw = self._query(FACTUAL_ACCURACY_SYSTEM, user_msg)
        label = str(raw.get("label", "NEI")).upper().strip()
        if label not in _VALID_LABELS:
            label = "NEI"
        score = 0.0 if label == "NEI" else _clamp(raw.get("score", 0))
        return {"label": label, "score": score, "reasoning": raw.get("reasoning", "")}

    def _score_closed(self, system: str, title: str, content: str) -> dict:
        user_msg = FC_CLOSED_USER.format(title=title, content=content)
        raw = self._query(system, user_msg)
        return {"score": _clamp(raw.get("score", 0)), "reasoning": raw.get("reasoning", "")}

    def _query(self, system: str, user: str) -> dict:
        return self._client.query_json(system, user)


def _clamp(value) -> float:
    return max(0.0, min(10.0, float(value)))


def fact_check_to_db_fields(result: FactCheckResult, judge_reasoning: str = "") -> dict:
    """Convert a FactCheckResult into fields for ArticleModel (fact_check_* columns)."""
    fc = result.fact_check
    return {
        "fact_check_score": result.fact_check_score,
        "fact_check_details": {
            "fact_check_score": result.fact_check_score,
            "sub_scores": {
                "factual_accuracy":           fc.factual_accuracy,
                "factual_accuracy_label":     fc.factual_accuracy_label,
                "factual_accuracy_reasoning": fc.factual_accuracy_reasoning,
                "accuracy_counted":           fc.accuracy_counted,
                "misleading_framing":         fc.misleading_framing,
                "misleading_framing_reasoning": fc.misleading_framing_reasoning,
                "missing_context":            fc.missing_context,
                "missing_context_reasoning":  fc.missing_context_reasoning,
            },
            "claims":   result.claims,
            "evidence": result.evidence,
            "judge_reasoning": judge_reasoning,
            "temperature": TEMPERATURE,
            "random_seed": RANDOM_SEED,
        },
        "fact_check_model":   FC_SCORE_MODEL_ID,
        "fact_check_version": FC_SCORE_VERSION,
        "fact_check_at":      datetime.now(timezone.utc),
    }
