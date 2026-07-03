"""
Data access for the dashboard — DB queries and highlight selection.
"""

from datetime import timedelta

import streamlit as st
from sqlalchemy import desc, func, select

from src import config
from src.db.connection import get_session
from src.db.models import ArticleModel

# Generous upper bound on "scored articles worth considering for the
# highlight" — pick_highlight() only looks 24h back from the latest score,
# and the pipeline fully scores at most a handful of articles per hour.
MAX_SCORED_ARTICLES = 500


@st.cache_data(ttl=60)
def load_articles() -> list[dict]:
    with get_session() as session:
        rows = list(session.scalars(
            select(ArticleModel)
            .where(ArticleModel.ragebait_score.isnot(None))
            .order_by(desc(ArticleModel.score_computed_at))
            .limit(MAX_SCORED_ARTICLES)
        ))
        return [
            {
                "id":               str(r.id),
                "title":            r.title or "",
                "url":              r.url,
                "category":         r.category or "—",
                "word_count":       r.word_count or 0,
                "scraped_at":       r.scraped_at,
                "score_computed_at": r.score_computed_at,
                "ragebait_score":   r.ragebait_score,
                "pre_score":        r.pre_score,
                "details":          r.score_details or {},
                "judge_reasoning":  (r.score_details or {}).get("judge", {}).get("reasoning"),
                "judge_selected":   (r.score_details or {}).get("judge", {}).get("selected", False),
                "score_model":      r.score_model or "—",
                "score_version":    r.score_version or "—",
            }
            for r in rows
        ]


@st.cache_data(ttl=60)
def load_batch_stats() -> dict:
    with get_session() as session:
        latest_scored = session.scalar(
            select(func.max(ArticleModel.pre_score_at))
        )
        if not latest_scored:
            return {"total": 0, "batch_time": None}
        window_start = latest_scored - timedelta(minutes=config.BATCH_WINDOW_MINUTES)
        total = session.scalar(
            select(func.count()).select_from(ArticleModel).where(
                ArticleModel.pre_score_at >= window_start,
            )
        )
        return {"total": total or 0, "batch_time": latest_scored}


@st.cache_data(ttl=60)
def load_factchecked() -> list[dict]:
    """Articles that have a grounded fact-check verdict (fact_check_score set)."""
    with get_session() as session:
        rows = list(session.scalars(
            select(ArticleModel)
            .where(ArticleModel.fact_check_score.isnot(None))
            .order_by(desc(ArticleModel.fact_check_at))
            .limit(MAX_SCORED_ARTICLES)
        ))
        out = []
        for r in rows:
            details = r.fact_check_details or {}
            out.append({
                "id":                 str(r.id),
                "title":              r.title or "",
                "url":                r.url,
                "category":           r.category or "—",
                "word_count":         r.word_count or 0,
                "scraped_at":         r.scraped_at,
                "fact_check_at":      r.fact_check_at,
                "fact_check_score":   r.fact_check_score,
                "fc_pre_score":       r.fc_pre_score,
                "details":            details,
                "sub_scores":         details.get("sub_scores", {}),
                "claims":             details.get("claims", []),
                "evidence":           details.get("evidence", []),
                "judge_reasoning":    details.get("judge_reasoning"),
                "skipped":            details.get("skipped"),
                "fact_check_model":   r.fact_check_model or "—",
                "fact_check_version": r.fact_check_version or "—",
            })
        return out


def pick_factcheck_highlight(articles: list[dict]) -> dict | None:
    """Most recent genuinely fact-checked article (skip the no-claim markers)."""
    scored = [a for a in articles if a.get("fact_check_at") and not a.get("skipped")]
    if not scored:
        return None
    return max(scored, key=lambda a: a["fact_check_at"])


@st.cache_data(ttl=60)
def load_factcheck_batch_stats() -> dict:
    """How many articles were pre-flagged in the latest fact-check screen window."""
    with get_session() as session:
        latest = session.scalar(select(func.max(ArticleModel.fc_pre_at)))
        if not latest:
            return {"total": 0, "batch_time": None}
        window_start = latest - timedelta(minutes=config.BATCH_WINDOW_MINUTES)
        total = session.scalar(
            select(func.count()).select_from(ArticleModel).where(
                ArticleModel.fc_pre_at >= window_start,
            )
        )
        return {"total": total or 0, "batch_time": latest}


def pick_highlight(articles: list[dict]) -> dict | None:
    """
    Pick the most notable article to highlight: the most recent judge-selected
    article, regardless of age — the card carries its own date. Mirrors the
    Faktencheck tab, which also shows its latest verdict instead of an empty
    state. The empty state only appears while no judge pick exists at all.
    """
    judged = [
        a for a in articles
        if a["score_computed_at"] is not None
        and a.get("judge_selected") and a.get("judge_reasoning")
    ]
    if not judged:
        return None
    return max(judged, key=lambda a: a["score_computed_at"])
