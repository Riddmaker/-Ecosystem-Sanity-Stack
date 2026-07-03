"""
Unit tests for pipeline orchestration — no network, no DB, no API.

Covers:
  - Source enablement: blick is registered but excluded from a default run.
  - Scrape watchdog: a hanging source is abandoned after
    config.SCRAPE_SOURCE_TIMEOUT and never freezes the rest of the run.
  - Winner selection: a single gate survivor still gets the judge block
    (dashboard eligibility) and out-of-range judge picks are clamped.
"""

import threading
from types import SimpleNamespace

from src import config, pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Source enablement
# ─────────────────────────────────────────────────────────────────────────────

def test_blick_registered_but_disabled_by_default():
    # Still reachable explicitly (e.g. local `--sources blick`)…
    assert "blick" in pipeline.CONNECTORS
    assert "blick" in pipeline.ALL_SOURCES
    # …but skipped by a default run because Akamai 403s datacenter IPs.
    assert "blick" in config.DISABLED_SOURCES
    assert "blick" not in pipeline.DEFAULT_SOURCES


def test_default_sources_keep_the_working_connectors():
    assert pipeline.DEFAULT_SOURCES == ["20min", "watson", "nau"]


# ─────────────────────────────────────────────────────────────────────────────
# Scrape watchdog
# ─────────────────────────────────────────────────────────────────────────────

class _FastConnector:
    SOURCE = "fast.test"

    def get_articles(self, since=None, max_articles=None):
        return ["fast-article"]


def test_scrape_abandons_hanging_source_and_continues(monkeypatch):
    """A source that overruns the timeout is skipped; the next source still runs."""
    release = threading.Event()

    class _HangingConnector:
        SOURCE = "hang.test"

        def get_articles(self, since=None, max_articles=None):
            # Blocks past the patched timeout; released in teardown so the
            # abandoned worker thread can exit cleanly (no atexit join stall).
            release.wait(timeout=10)
            return ["should-never-be-collected"]

    monkeypatch.setattr(config, "SCRAPE_SOURCE_TIMEOUT", 0.3)
    monkeypatch.setattr(
        pipeline, "CONNECTORS",
        {"hang": _HangingConnector, "fast": _FastConnector},
    )

    try:
        result = pipeline._scrape(["hang", "fast"], since=None, max_articles=None)
        # Hanging source contributed nothing; fast source ran normally.
        assert result == ["fast-article"]
    finally:
        release.set()


# ─────────────────────────────────────────────────────────────────────────────
# Winner selection (judge)
# ─────────────────────────────────────────────────────────────────────────────

class _StubScorer:
    def __init__(self, chosen=1):
        self._chosen = chosen

    def judge_articles(self, judge_input):
        return {"chosen": self._chosen, "reasoning": "Die Headline inszeniert Empörung."}


class _StubSession:
    def flush(self):
        pass


def _scored_candidate(title="Testartikel"):
    # Content below MIN_ARTICLE_WORDS keeps _attach_reader_service a no-op,
    # so no scorer.generate_reader_service stub is needed.
    article = SimpleNamespace(title=title, content="kurz", score_details=None)
    result = SimpleNamespace(
        ragebait_score=6.0,
        ragebait=SimpleNamespace(
            curiosity_gap=5.0,
            conflict_staging=4.0,
            emotional_inflation=6.0,
            narrative_exploitation=7.0,
            reasoning="trace",
        ),
    )
    return article, result


def test_pick_winner_marks_single_candidate_judge_selected():
    """A single gate survivor must still get the judge block — the dashboard
    highlight (data.pick_highlight) only ever shows judge-selected articles."""
    article, result = _scored_candidate()
    winner, winner_result = pipeline._pick_winner(
        _StubScorer(), _StubSession(), [(article, result)]
    )
    assert winner is article
    assert winner_result is result
    judge = article.score_details["judge"]
    assert judge["selected"] is True
    assert judge["reasoning"]


def test_pick_winner_clamps_out_of_range_judge_pick():
    """An out-of-range chosen index is clamped instead of discarding the verdict."""
    article, result = _scored_candidate()
    winner, _ = pipeline._pick_winner(
        _StubScorer(chosen=7), _StubSession(), [(article, result)]
    )
    assert winner is article
    assert article.score_details["judge"]["selected"] is True
