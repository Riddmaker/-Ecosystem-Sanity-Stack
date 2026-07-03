"""
Unit tests for src/analysis/hard_metrics.py — deterministic, no LLM, no network.

The metrics feed the MESSWERTE prompt block and are persisted under
score_details/fact_check_details.hard_metrics, so they must be stable,
JSON-serialisable and linguistically sane on German fixtures.
"""

import json

from src.analysis import hard_metrics as hm

RAGEBAIT_TITLE = "Diese Frau trotzt der Kritik — die Community ist gespalten!"
RAGEBAIT_TEXT = (
    "Ein Skandal erschüttert die Szene: Das Opfer bleibt schutzlos zurück, "
    "die Behörde hat versagt. «Ich bin empört», sagte eine Anwohnerin. "
    "Was meint ihr?"
)

SOBER_TITLE = "Nationalrat lehnt Initiative mit 120 zu 68 Stimmen ab"
SOBER_TEXT = (
    "Der Nationalrat hat die Initiative am Dienstag mit 120 zu 68 Stimmen "
    "abgelehnt. Laut der Bundeskanzlei kündigten die Befürworter an, das "
    "Referendum zu prüfen. Im Vorjahr scheiterte ein ähnlicher Vorstoss. "
    "Die Gegner hingegen verteidigen den Entscheid."
)


# ── quote handling ───────────────────────────────────────────────────────────

def test_strip_quotes_removes_quoted_speech():
    stripped = hm.strip_quotes(RAGEBAIT_TEXT)
    assert "empört" not in stripped          # inside «...» — not editorial voice
    assert "Skandal" in stripped             # editorial voice stays


def test_quoted_emotive_words_do_not_count_as_editorial():
    metrics = hm.ragebait_metrics(RAGEBAIT_TITLE, RAGEBAIT_TEXT)
    assert "skandal" in metrics["editorial_emotive_hits"]
    assert "empört" not in metrics["editorial_emotive_hits"]


# ── ragebait metrics ─────────────────────────────────────────────────────────

def test_ragebait_metrics_fire_on_manufactured_emotion():
    metrics = hm.ragebait_metrics(RAGEBAIT_TITLE, RAGEBAIT_TEXT)
    assert metrics["title_forward_reference_hits"]          # "Diese Frau …"
    assert metrics["title_exclamations"] == 1
    assert "gespalten" in metrics["engagement_marker_hits"]
    assert "was meint ihr" in metrics["engagement_marker_hits"]
    assert "opfer" in metrics["moral_word_hits"]
    assert "versagt" in metrics["moral_word_hits"]
    assert metrics["emotive_per_1000_words"] > 0


def test_ragebait_metrics_stay_quiet_on_sober_reporting():
    metrics = hm.ragebait_metrics(SOBER_TITLE, SOBER_TEXT)
    assert metrics["title_forward_reference_hits"] == []
    assert metrics["title_exclamations"] == 0
    assert metrics["engagement_marker_hits"] == []
    assert metrics["editorial_emotive_hits"] == []
    assert metrics["headline_body_overlap_pct"] > 50.0      # headline grounded


# ── fact-check metrics ───────────────────────────────────────────────────────

def test_factcheck_metrics_detect_context_signals():
    metrics = hm.factcheck_metrics(SOBER_TITLE, SOBER_TEXT)
    assert metrics["number_tokens"] >= 2                     # 120, 68
    assert "vorjahr" in metrics["comparison_anchor_hits"]
    assert "laut" in metrics["attribution_hits"]
    assert "hingegen" in metrics["counterposition_hits"]


def test_factcheck_metrics_flag_naked_numbers():
    text = "Die Delikte stiegen um 40 Prozent. Anwohner zeigen sich besorgt."
    metrics = hm.factcheck_metrics("Kriminalität explodiert", text)
    assert metrics["percent_tokens"] == 1
    assert metrics["comparison_anchor_hits"] == []           # no baseline anchor
    assert metrics["counterposition_hits"] == []              # nobody else speaks


# ── evidence metrics ─────────────────────────────────────────────────────────

def test_evidence_metrics_coverage_counts():
    claims = ["A", "B", "C"]
    evidence = [
        {"claim": "A", "fact_checks": [{"rating": "Falsch"}], "web_evidence": []},
        {"claim": "B", "fact_checks": [], "web_evidence": [
            {"score": 0.8}, {"score": 0.6}]},
        {"claim": "C", "fact_checks": [], "web_evidence": []},
    ]
    metrics = hm.evidence_metrics(claims, evidence)
    assert metrics["claims_total"] == 3
    assert metrics["claims_with_factcheck_hits"] == 1
    assert metrics["claims_with_web_evidence"] == 1
    assert metrics["claims_without_evidence"] == 1
    assert metrics["evidence_sources_total"] == 3
    assert metrics["mean_web_relevance"] == 0.7


def test_evidence_metrics_empty_inputs():
    metrics = hm.evidence_metrics([], [])
    assert metrics["claims_total"] == 0
    assert metrics["mean_web_relevance"] == 0.0


# ── rendering + persistence contract ─────────────────────────────────────────

def test_render_metrics_block_is_deterministic_and_labelled():
    metrics = hm.ragebait_metrics(RAGEBAIT_TITLE, RAGEBAIT_TEXT)
    block1 = hm.render_metrics_block(metrics)
    block2 = hm.render_metrics_block(hm.ragebait_metrics(RAGEBAIT_TITLE, RAGEBAIT_TEXT))
    assert block1 == block2                                   # byte-stable
    assert block1.count("\n") + 1 == len(block1.splitlines())
    assert all(line.startswith("- ") for line in block1.splitlines())
    assert "Engagement-Marker" in block1                      # German labels active


def test_metrics_are_json_serialisable():
    for metrics in (
        hm.ragebait_metrics(RAGEBAIT_TITLE, RAGEBAIT_TEXT),
        hm.factcheck_metrics(SOBER_TITLE, SOBER_TEXT),
        hm.evidence_metrics(["A"], []),
    ):
        json.dumps(metrics)                                   # JSONB-ready


def test_metrics_handle_empty_text():
    metrics = hm.ragebait_metrics("", "")
    assert metrics["word_count"] == 0
    assert metrics["emotive_per_1000_words"] == 0.0
    assert hm.render_metrics_block(metrics)                   # still renders
