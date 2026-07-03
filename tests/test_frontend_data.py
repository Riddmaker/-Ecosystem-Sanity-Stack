"""
Unit tests for dashboard data helpers — highlight selection (no DB).

pick_highlight must mirror the Faktencheck tab: show the most recent
judge-selected article regardless of age (the card carries its own date),
and only fall back to the empty state while no judge pick exists at all.
"""

from datetime import datetime, timedelta, timezone

from src.frontend.data import pick_highlight

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


def _article(ts, judged=False, **overrides):
    article = {
        "score_computed_at": ts,
        "judge_selected": judged,
        "judge_reasoning": "Die Headline inszeniert Empörung." if judged else None,
    }
    article.update(overrides)
    return article


def test_pick_highlight_returns_most_recent_judge_pick():
    older = _article(NOW - timedelta(days=5), judged=True)
    newer = _article(NOW - timedelta(days=3), judged=True)
    assert pick_highlight([older, newer]) is newer


def test_pick_highlight_shows_old_judge_pick_instead_of_empty_state():
    # Regression: the old 24h window blanked the dashboard whenever the most
    # recent runs gated everything out, even though a judge pick existed.
    stale = _article(NOW - timedelta(days=6), judged=True)
    assert pick_highlight([stale]) is stale


def test_pick_highlight_ignores_newer_unjudged_articles():
    # Scored-but-unjudged articles must neither win nor blank the dashboard.
    judged = _article(NOW - timedelta(days=2), judged=True)
    fresh_unjudged = _article(NOW)
    assert pick_highlight([fresh_unjudged, judged]) is judged


def test_pick_highlight_empty_without_any_judge_pick():
    assert pick_highlight([]) is None
    assert pick_highlight([_article(NOW)]) is None
    # judge_selected without reasoning does not qualify (nothing to render)
    assert pick_highlight([_article(NOW, judged=True, judge_reasoning=None)]) is None
