"""
Deterministic text metrics ("hard metrics") for both scoring tracks.

Pure Python — no LLM, no network, no new dependencies. Tier-2 scoring computes
these counts/ratios from the exact text the model sees and injects them into
the prompts as a MESSWERTE block (render_metrics_block), so the LLM grounds
its marker decisions in measured signals instead of impressions. The raw dicts
are persisted under score_details.hard_metrics / fact_check_details.hard_metrics.

Paper anchors per metric group:
  curiosity gap          — Blom & Hansen (2015): forward references in headlines
  conflict staging       — Rony et al. (2017): engagement-farming markers
  emotional inflation    — Potthast et al. (2016): emotive wording density
  narrative exploitation — Brady et al. (2017): moral-emotional vocabulary
  misleading framing     — Entman (1993): salience via headline/body divergence
  missing context        — Rogers et al. (2017): naked numbers, absent counter-voices
  factual accuracy       — FEVER (Thorne et al. 2018): evidence coverage stats

The word lists / patterns live in src.strings (language-specific — the English
mirror carries English equivalents), so a language switch swaps them too.
"""

import re

from src.strings import (
    HM_ATTRIBUTION_PATTERNS,
    HM_COMPARISON_ANCHORS,
    HM_COUNTERPOSITION_MARKERS,
    HM_EMOTIVE_WORDS,
    HM_ENGAGEMENT_PATTERNS,
    HM_FORWARD_REFERENCE_PATTERNS,
    HM_LABELS,
    HM_MORAL_WORDS,
    HM_NO,
    HM_YES,
)

# Quoted speech spans — excluded where a metric targets the *editorial* voice.
_QUOTE_SPANS = re.compile(r"«[^»]*»|„[^“”]*[“”]|\"[^\"]*\"|‹[^›]*›")

_WORD = re.compile(r"\b\w+\b", re.UNICODE)
_NUMBER_TOKEN = re.compile(r"\b\d+(?:['’.,]\d+)*\b")
_PERCENT_TOKEN = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|prozent|percent)", re.IGNORECASE)

_FORWARD_REFERENCE = [re.compile(p, re.IGNORECASE) for p in HM_FORWARD_REFERENCE_PATTERNS]


def strip_quotes(text: str) -> str:
    """Remove quoted speech so lexicon hits reflect the editorial voice only."""
    return _QUOTE_SPANS.sub(" ", text or "")


def _word_hits(text: str, lexicon: list[str]) -> list[str]:
    """Unique lexicon entries found on word boundaries, in lexicon order."""
    lowered = " " + (text or "").lower() + " "
    hits: list[str] = []
    for entry in lexicon:
        if re.search(r"\b" + re.escape(entry) + r"\b", lowered):
            hits.append(entry)
    return hits


def _occurrences(text: str, lexicon: list[str]) -> int:
    """Total lexicon matches including repeats (for density metrics)."""
    lowered = " " + (text or "").lower() + " "
    return sum(
        len(re.findall(r"\b" + re.escape(entry) + r"\b", lowered))
        for entry in lexicon
    )


def _per_1000_words(count: int, text: str) -> float:
    words = len(_WORD.findall(text or ""))
    return round(count * 1000.0 / words, 1) if words else 0.0


def quote_share_pct(text: str) -> float:
    """Share of characters inside quoted speech (0–100)."""
    if not text:
        return 0.0
    quoted = sum(len(m.group(0)) for m in _QUOTE_SPANS.finditer(text))
    return round(100.0 * quoted / len(text), 1)


def headline_body_overlap_pct(title: str, content: str, body_words: int = 80) -> float:
    """
    Share of the headline's content words (>=4 chars) that reappear in the
    article's first `body_words` words. Low overlap = the headline promises or
    claims things the opening never grounds (salience / forward reference).
    """
    title_words = {w.lower() for w in _WORD.findall(title or "") if len(w) >= 4}
    if not title_words:
        return 100.0
    body = {w.lower() for w in _WORD.findall(content or "")[:body_words]}
    return round(100.0 * len(title_words & body) / len(title_words), 1)


# ── Aggregators ──────────────────────────────────────────────────────────────

def ragebait_metrics(title: str, content: str) -> dict:
    """Deterministic signals for the four ragebait sub-scores."""
    editorial = strip_quotes(content)
    emotive = _word_hits(editorial, HM_EMOTIVE_WORDS)
    moral = _word_hits(editorial, HM_MORAL_WORDS)
    return {
        "title_is_question": (title or "").rstrip().endswith("?"),
        "title_exclamations": (title or "").count("!"),
        "title_forward_reference_hits": [
            match.group(0).strip()
            for p in _FORWARD_REFERENCE
            if (match := p.search(title or ""))
        ],
        "headline_body_overlap_pct": headline_body_overlap_pct(title, content),
        # Title included — "Community gespalten" style staging lives in headlines
        "engagement_marker_hits": _word_hits(f"{title or ''} {content or ''}", HM_ENGAGEMENT_PATTERNS),
        "editorial_emotive_hits": emotive,
        "emotive_per_1000_words": _per_1000_words(
            _occurrences(editorial, HM_EMOTIVE_WORDS), editorial
        ),
        "moral_word_hits": moral,
        "moral_per_1000_words": _per_1000_words(
            _occurrences(editorial, HM_MORAL_WORDS), editorial
        ),
        "quote_share_pct": quote_share_pct(content),
        "word_count": len(_WORD.findall(content or "")),
    }


def factcheck_metrics(title: str, content: str) -> dict:
    """Deterministic signals for the framing / missing-context sub-scores."""
    editorial = strip_quotes(content)
    emotive = _word_hits(editorial, HM_EMOTIVE_WORDS)
    attribution = _word_hits(content, HM_ATTRIBUTION_PATTERNS)
    return {
        "headline_body_overlap_pct": headline_body_overlap_pct(title, content),
        "editorial_emotive_hits": emotive,
        "emotive_per_1000_words": _per_1000_words(
            _occurrences(editorial, HM_EMOTIVE_WORDS), editorial
        ),
        "number_tokens": len(_NUMBER_TOKEN.findall(content or "")),
        "percent_tokens": len(_PERCENT_TOKEN.findall(content or "")),
        "comparison_anchor_hits": _word_hits(content, HM_COMPARISON_ANCHORS),
        "attribution_hits": attribution,
        "counterposition_hits": _word_hits(content, HM_COUNTERPOSITION_MARKERS),
        "quote_share_pct": quote_share_pct(content),
        "word_count": len(_WORD.findall(content or "")),
    }


def evidence_metrics(claims: list[str], evidence: list[dict]) -> dict:
    """Coverage statistics over the retrieved evidence (FEVER-style grounding)."""
    with_fc = with_web = sources = 0
    relevances: list[float] = []
    for bundle in evidence or []:
        fcs = bundle.get("fact_checks") or []
        web = bundle.get("web_evidence") or []
        with_fc += bool(fcs)
        with_web += bool(web)
        sources += len(fcs) + len(web)
        relevances.extend(w.get("score", 0.0) for w in web if isinstance(w, dict))
    covered = sum(
        bool((b.get("fact_checks") or []) or (b.get("web_evidence") or []))
        for b in evidence or []
    )
    return {
        "claims_total": len(claims or []),
        "claims_with_factcheck_hits": with_fc,
        "claims_with_web_evidence": with_web,
        "claims_without_evidence": max(len(claims or []) - covered, 0),
        "evidence_sources_total": sources,
        "mean_web_relevance": round(sum(relevances) / len(relevances), 2) if relevances else 0.0,
    }


# ── Prompt rendering ─────────────────────────────────────────────────────────

def render_metrics_block(metrics: dict) -> str:
    """
    Render a metrics dict as deterministic "- Label: value" lines for the
    MESSWERTE prompt block. Labels come from strings.HM_LABELS (language-
    specific); keys without a label are skipped. Rendering order follows
    HM_LABELS so the block is byte-stable for identical inputs.
    """
    lines: list[str] = []
    for key, label in HM_LABELS.items():
        if key not in metrics:
            continue
        value = metrics[key]
        if isinstance(value, bool):
            rendered = HM_YES if value else HM_NO
        elif isinstance(value, list):
            if not value:
                rendered = "—"
            else:
                shown = ", ".join(f"«{v}»" for v in value[:8])
                rendered = shown + (f" (+{len(value) - 8})" if len(value) > 8 else "")
        elif isinstance(value, float):
            rendered = f"{value:.1f}"
        else:
            rendered = str(value)
        lines.append(f"- {label}: {rendered}")
    return "\n".join(lines)
