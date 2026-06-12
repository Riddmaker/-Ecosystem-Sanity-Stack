"""
Unit tests for pipeline orchestration — no network, no DB, no API.

Covers:
  - Source enablement: blick is registered but excluded from a default run.
  - Scrape watchdog: a hanging source is abandoned after
    config.SCRAPE_SOURCE_TIMEOUT and never freezes the rest of the run.
"""

import threading

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
