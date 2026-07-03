"""
MediaScorer — scores a news article on the Ragebait Index via Mistral Large.

Four sub-scores are computed in parallel (one API call each):
  curiosity_gap          — Blom & Hansen (2015)
  conflict_staging       — Rony et al. (2017)
  emotional_inflation    — Potthast et al. (2016)
  narrative_exploitation — Brady et al. (2017)

Composite score = mean of the four sub-scores.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from src.analysis.hard_metrics import ragebait_metrics, render_metrics_block
from src.scoring.llm_client import MistralJSONClient, RANDOM_SEED, TEMPERATURE
from src.scoring.schemas import RagebaitScore, ScoreResult
from src.scoring.throttle import large_limiter
from src.strings import (
    SUB_SCORE_USER,
    CURIOSITY_GAP_SYSTEM,
    CONFLICT_STAGING_SYSTEM,
    EMOTIONAL_INFLATION_SYSTEM,
    NARRATIVE_EXPLOITATION_SYSTEM,
    READER_SERVICE_SYSTEM,
    READER_SERVICE_USER,
    JUDGE_SYSTEM,
    JUDGE_USER,
    GATE_SYSTEM,
    GATE_USER,
)

SCORE_MODEL_ID    = "mistral-large-latest"
SCORE_VERSION     = "v10"   # v10: deterministic MESSWERTE block fed to the sub-scores
MAX_CONTENT_CHARS = 3000

_SUB_TASKS = [
    ("curiosity_gap",          CURIOSITY_GAP_SYSTEM),
    ("conflict_staging",       CONFLICT_STAGING_SYSTEM),
    ("emotional_inflation",    EMOTIONAL_INFLATION_SYSTEM),
    ("narrative_exploitation", NARRATIVE_EXPLOITATION_SYSTEM),
]


class MediaScorer:
    """
    Scores a news article on the Ragebait Index.

    Four sub-score API calls are fired in parallel, then aggregated.

    Usage:
        scorer = MediaScorer()
        result = scorer.score(title="...", content="...")
    """

    def __init__(self, api_key: Optional[str] = None, model: str = SCORE_MODEL_ID):
        self._client = MistralJSONClient(model, large_limiter, api_key)

    def score(self, title: str, content: str) -> ScoreResult:
        """Fire 4 parallel sub-score calls and return an aggregated ScoreResult."""
        content_trunc = content[:MAX_CONTENT_CHARS]
        # Deterministic signals over the exact text the model sees — injected
        # into every sub-score prompt and persisted alongside the verdict.
        hard_metrics = ragebait_metrics(title, content_trunc)
        metrics_block = render_metrics_block(hard_metrics)

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_map = {
                executor.submit(
                    self._score_sub, system, title, content_trunc, metrics_block
                ): key
                for key, system in _SUB_TASKS
            }
            sub_scores: dict[str, dict] = {}
            for future in as_completed(future_map):
                key = future_map[future]
                sub_scores[key] = future.result()

        cg = sub_scores["curiosity_gap"]
        cs = sub_scores["conflict_staging"]
        ei = sub_scores["emotional_inflation"]
        ne = sub_scores["narrative_exploitation"]

        composite = (cg["score"] + cs["score"] + ei["score"] + ne["score"]) / 4.0

        # Combined reasoning kept for backward-compat display fallback
        reasoning = (
            f"curiosity_gap-{cg['reasoning']} "
            f"conflict_staging-{cs['reasoning']} "
            f"emotional_inflation-{ei['reasoning']} "
            f"narrative_exploitation-{ne['reasoning']}"
        )

        ragebait = RagebaitScore(
            score=composite,
            curiosity_gap=cg["score"],
            curiosity_gap_reasoning=cg["reasoning"],
            conflict_staging=cs["score"],
            conflict_staging_reasoning=cs["reasoning"],
            emotional_inflation=ei["score"],
            emotional_inflation_reasoning=ei["reasoning"],
            narrative_exploitation=ne["score"],
            narrative_exploitation_reasoning=ne["reasoning"],
            reasoning=reasoning,
        )

        return ScoreResult(
            ragebait_score=composite,
            ragebait=ragebait,
            reasoning=reasoning,
            hard_metrics=hard_metrics,
        )

    def gate_article(self, title: str, content: str) -> dict:
        """
        Qualitative gate: does the editorial treatment inflate emotional weight
        beyond what the facts alone warrant?

        Returns {"pass": bool, "reasoning": str}
        pass=True  → article deserves full scoring
        pass=False → emotional weight comes from the facts, not editorial choices
        """
        user_msg = GATE_USER.format(title=title, content=content[:MAX_CONTENT_CHARS])
        raw = self._query(GATE_SYSTEM, user_msg)
        passed = bool(raw.get("pass", True))
        return {"pass": passed, "reasoning": raw.get("reasoning", "")}

    def generate_reader_service(self, title: str, content: str, score_result: "ScoreResult") -> dict:
        """
        Generate a factual extract for the judge-picked article.
        Only called when ragebait_score >= 5.0.

        Returns {"facts": str, "stake": str, "action": str}
        """
        rb = score_result.ragebait
        user_msg = READER_SERVICE_USER.format(
            title=title,
            content=content[:MAX_CONTENT_CHARS],
            ragebait_score=score_result.ragebait_score,
            curiosity_gap=rb.curiosity_gap,
            conflict_staging=rb.conflict_staging,
            emotional_inflation=rb.emotional_inflation,
            narrative_exploitation=rb.narrative_exploitation,
        )
        raw = self._query(READER_SERVICE_SYSTEM, user_msg)
        action = raw.get("action", "")
        if isinstance(action, dict):
            action = " ".join(v for v in action.values() if isinstance(v, str))
        return {
            "facts":  raw.get("facts", ""),
            "stake":  raw.get("stake", ""),
            "action": action,
        }

    def judge_articles(self, scored: list[dict]) -> dict:
        """
        Qualitative winner selection across already-scored candidates.

        Args:
            scored: list of dicts with keys:
                      title, ragebait_score, curiosity_gap, conflict_staging,
                      emotional_inflation, narrative_exploitation, reasoning

        Returns:
            {"chosen": int (1-indexed), "reasoning": str}
        """
        lines = []
        for i, a in enumerate(scored, start=1):
            lines.append(
                f"[Artikel {i}]\n"
                f"Titel: «{a['title']}»\n"
                f"Ragebait-Score: {a['ragebait_score']:.1f}\n"
                f"Curiosity Gap: {a['curiosity_gap']:.1f} | "
                f"Conflict Staging: {a['conflict_staging']:.1f} | "
                f"Emotional Inflation: {a['emotional_inflation']:.1f} | "
                f"Narrative Exploitation: {a['narrative_exploitation']:.1f}\n"
                f"Scoring-Reasoning: \"{a['reasoning']}\""
            )
        articles_block = "\n\n".join(lines)
        user_msg = JUDGE_USER.format(n=len(scored), articles=articles_block)
        raw = self._query(JUDGE_SYSTEM, user_msg)

        chosen = int(raw.get("chosen", 1))
        chosen = max(1, min(chosen, len(scored)))
        return {"chosen": chosen, "reasoning": raw.get("reasoning", "")}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_sub(self, system: str, title: str, content: str, metrics_block: str) -> dict:
        """Score a single sub-dimension. Returns {"score": float, "reasoning": str}."""
        user_msg = SUB_SCORE_USER.format(title=title, content=content, metrics=metrics_block)
        raw = self._query(system, user_msg)
        score = float(raw.get("score", 0))
        score = max(0.0, min(10.0, score))
        return {"score": score, "reasoning": raw.get("reasoning", "")}

    def _query(self, system: str, user: str) -> dict:
        return self._client.query_json(system, user)


def result_to_db_fields(result: ScoreResult) -> dict:
    """Convert a ScoreResult into fields for ArticleModel."""
    rb = result.ragebait
    return {
        "ragebait_score": result.ragebait_score,
        "score_details": {
            "ragebait_score": result.ragebait_score,
            "ragebait": {
                "score":                          rb.score,
                "curiosity_gap":                  rb.curiosity_gap,
                "curiosity_gap_reasoning":         rb.curiosity_gap_reasoning,
                "conflict_staging":               rb.conflict_staging,
                "conflict_staging_reasoning":      rb.conflict_staging_reasoning,
                "emotional_inflation":            rb.emotional_inflation,
                "emotional_inflation_reasoning":   rb.emotional_inflation_reasoning,
                "narrative_exploitation":         rb.narrative_exploitation,
                "narrative_exploitation_reasoning": rb.narrative_exploitation_reasoning,
                "reasoning":                      rb.reasoning,
            },
            "hard_metrics": result.hard_metrics,
            "temperature": TEMPERATURE,
            "random_seed": RANDOM_SEED,
        },
        "score_model":       SCORE_MODEL_ID,
        "score_version":     SCORE_VERSION,
        "score_computed_at": datetime.now(timezone.utc),
    }
