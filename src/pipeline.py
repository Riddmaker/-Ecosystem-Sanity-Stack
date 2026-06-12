"""
Core pipeline logic — importable function so it can be called from both
the CLI (run_pipeline.py) and the scheduler (scheduler.py).

Stages: scrape → upsert → pre-screen → gate → full-score → judge.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from src import config
from src.connectors.abstract.models import Article
from src.db.connection import get_session, init_db
from src.db.models import ArticleModel
from src.db.repository import ArticleRepository
from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
    TwentyMinutesScraperConnector,
)
from src.connectors.specific_scraper.watson_scraper_connector import WatsonScraperConnector
from src.connectors.specific_scraper.blick_scraper_connector import BlickScraperConnector
from src.connectors.specific_scraper.nau_scraper_connector import NauScraperConnector
from src.scoring.pre_scorer import PreScorer, pre_score_to_db_fields
from src.scoring.schemas import ScoreResult
from src.scoring.scorer import MediaScorer, result_to_db_fields

log = logging.getLogger(__name__)

CONNECTORS = {
    "20min":  TwentyMinutesScraperConnector,
    "watson": WatsonScraperConnector,
    "blick":  BlickScraperConnector,
    "nau":    NauScraperConnector,
}
ALL_SOURCES = list(CONNECTORS)


def is_paywalled(article: ArticleModel) -> bool:
    """
    Paywalled / teaser-only article? Scoring truncated marketing copy
    inflates every dimension artificially and causes hallucinations.
    """
    word_count = article.word_count or len((article.content or "").split())
    return (
        config.PAYWALL_TITLE_MARKER in (article.title or "").lower()
        or word_count < config.MIN_ARTICLE_WORDS
    )


def _scrape(
    sources: list[str],
    since: Optional[datetime],
    max_articles: Optional[int],
) -> list[Article]:
    """Run every requested connector; a failing source never aborts the run."""
    all_articles: list[Article] = []
    for name in sources:
        connector_cls = CONNECTORS[name]
        log.info("Scraping %s", connector_cls.SOURCE)
        try:
            fetched = connector_cls().get_articles(since=since, max_articles=max_articles)
            all_articles.extend(fetched)
            log.info("%s: %d articles", connector_cls.SOURCE, len(fetched))
        except Exception:
            log.exception("Scrape failed for %s", connector_cls.SOURCE)
    return all_articles


def _prescreen(new_or_updated_urls: list[str]) -> None:
    """Tier 1: pre-score every new/changed article with Mistral Small."""
    pre_scorer = PreScorer()
    with get_session() as session:
        repo = ArticleRepository(session)
        for article in repo.get_unprescored(urls=new_or_updated_urls):
            if is_paywalled(article):
                # Mark as screened so it doesn't requeue every run
                article.pre_score = 0.0
                article.pre_score_reasoning = "SKIP: paywalled or teaser-only content"
                article.pre_score_model = "none"
                article.pre_score_at = datetime.now(timezone.utc)
                session.flush()
                log.info("[paywall] %s", (article.title or "")[:60])
                continue

            try:
                result = pre_scorer.score(
                    title=article.title or "", content=article.content or ""
                )
                for k, v in pre_score_to_db_fields(result).items():
                    setattr(article, k, v)
                session.flush()
                log.info("%.1f  %s", result.score, (article.title or "")[:60])
            except Exception:
                log.exception("Pre-score failed: %s", (article.title or "")[:60])


def _gate(scorer: MediaScorer, gate_candidates: list[ArticleModel]) -> list[ArticleModel]:
    """Qualitative gate: keep only articles with genuine editorial inflation."""
    passed: list[ArticleModel] = []
    for gc in gate_candidates:
        try:
            gate = scorer.gate_article(title=gc.title or "", content=gc.content or "")
            verdict = "PASS" if gate["pass"] else "SKIP"
            log.info('[%s] pre=%.1f  "%s"', verdict, gc.pre_score, (gc.title or "")[:55])
            log.info("       %s", gate["reasoning"][:100])
            if gate["pass"]:
                passed.append(gc)
        except Exception:
            log.exception("Gate failed: %s", (gc.title or "")[:55])
            passed.append(gc)  # on gate error, include to be safe
    return passed


def _full_score(
    scorer: MediaScorer,
    session,
    candidates: list[ArticleModel],
) -> list[tuple[ArticleModel, ScoreResult]]:
    """Tier 2: four parallel sub-scores per candidate with Mistral Large."""
    scored: list[tuple[ArticleModel, ScoreResult]] = []
    for candidate in candidates:
        log.info('Scoring: "%s"', (candidate.title or "")[:60])
        try:
            result = scorer.score(
                title=candidate.title or "", content=candidate.content or ""
            )
            for k, v in result_to_db_fields(result).items():
                setattr(candidate, k, v)
            session.flush()
            log.info("   ragebait=%.1f", result.ragebait_score)
            scored.append((candidate, result))
        except Exception:
            log.exception("Scoring failed: %s", (candidate.title or "")[:60])
    return scored


def _pick_winner(
    scorer: MediaScorer,
    session,
    scored: list[tuple[ArticleModel, ScoreResult]],
) -> tuple[ArticleModel, ScoreResult]:
    """
    Judge: qualitative winner selection across the scored candidates.
    Persists the judge verdict and a reader-service extract on the winner.
    Falls back to the highest ragebait_score if the judge call fails.
    """
    judge_input = [
        {
            "title":                  c.title or "",
            "ragebait_score":         r.ragebait_score,
            "curiosity_gap":          r.ragebait.curiosity_gap,
            "conflict_staging":       r.ragebait.conflict_staging,
            "emotional_inflation":    r.ragebait.emotional_inflation,
            "narrative_exploitation": r.ragebait.narrative_exploitation,
            "reasoning":              r.ragebait.reasoning,
        }
        for c, r in scored
    ]
    try:
        judge_result = scorer.judge_articles(judge_input)
        idx = judge_result["chosen"] - 1  # 0-indexed
        winner_article, winner_result = scored[idx]
        judge_reasoning = judge_result["reasoning"]
        log.info('Judge chose Artikel %d: "%s"', judge_result["chosen"],
                 (winner_article.title or "")[:70])
        log.info("Reasoning: %s", judge_reasoning)

        winner_article.score_details = {
            **(winner_article.score_details or {}),
            "judge": {
                "selected":  True,
                "reasoning": judge_reasoning,
            },
        }
        session.flush()

        _attach_reader_service(scorer, session, winner_article, winner_result)
    except Exception:
        log.exception("Judge failed — falling back to highest ragebait_score")
        idx = max(range(len(scored)), key=lambda i: scored[i][1].ragebait_score)
        winner_article, winner_result = scored[idx]

    return winner_article, winner_result


def _attach_reader_service(
    scorer: MediaScorer,
    session,
    winner_article: ArticleModel,
    winner_result: ScoreResult,
) -> None:
    """Factual extract for the judge-picked article, skipped for thin content."""
    content_words = len((winner_article.content or "").split())
    if content_words < config.MIN_READER_SERVICE_WORDS:
        log.info(
            "Skipping reader service — content too short (%d words, likely paywalled teaser)",
            content_words,
        )
        return
    try:
        log.info("Generating reader service (ragebait=%.1f)...", winner_result.ragebait_score)
        reader_service = scorer.generate_reader_service(
            title=winner_article.title or "",
            content=winner_article.content or "",
            score_result=winner_result,
        )
        winner_article.score_details = {
            **(winner_article.score_details or {}),
            "reader_service": reader_service,
        }
        session.flush()
    except Exception:
        log.exception("Reader service failed")


def run(
    hours: Optional[float] = None,
    max_articles: Optional[int] = None,
    sources: Optional[list[str]] = None,
) -> bool:
    """
    Run the full pipeline: scrape → upsert → pre-screen → gate → full-score → judge.

    Args:
        hours:        Only include articles published within the last N hours.
        max_articles: Hard cap on articles fetched per source.
        sources:      Which sources to scrape. Defaults to all of them.

    Returns:
        True if at least one article was fully scored, False otherwise.
    """
    if sources is None:
        sources = ALL_SOURCES

    init_db()

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours) if hours else None

    log.info("Pipeline start %s", now.strftime("%Y-%m-%d %H:%M UTC"))
    if since:
        log.info("Filter: articles since %s (--hours %s)", since.strftime("%H:%M UTC"), hours)
    if max_articles:
        log.info("Cap: max %d articles per source", max_articles)
    log.info("Sources: %s", ", ".join(sources))

    # ── 1. Scrape ────────────────────────────────────────────────
    log.info("[1/4] Scraping sources...")
    all_articles = _scrape(sources, since, max_articles)
    log.info("Total: %d articles across all sources", len(all_articles))

    # ── 2. Upsert ────────────────────────────────────────────────
    log.info("[2/4] Upserting to DB...")
    with get_session() as session:
        results = ArticleRepository(session).upsert_many(all_articles)
    new_or_updated_urls = [url for url, changed in results.items() if changed]
    log.info(
        "%d new/updated   %d unchanged",
        len(new_or_updated_urls), len(results) - len(new_or_updated_urls),
    )

    # ── 3. Pre-screen ────────────────────────────────────────────
    log.info("[3/4] Pre-screening %d articles with Mistral Small...", len(new_or_updated_urls))
    if new_or_updated_urls:
        _prescreen(new_or_updated_urls)
    else:
        log.info("Nothing to pre-score.")

    # ── 4. Gate → full-score → judge ─────────────────────────────
    log.info("[4/4] Qualitative gate + full-scoring with Mistral Large...")
    scored: list[tuple[ArticleModel, ScoreResult]] = []
    with get_session() as session:
        repo = ArticleRepository(session)
        gate_candidates = repo.get_prescored_above_threshold(
            min_score=config.GATE_MIN_PRE_SCORE,
            limit=config.GATE_CANDIDATE_LIMIT,
        )

        if not gate_candidates:
            log.info("No candidates above pre-score threshold.")
        else:
            scorer = MediaScorer()

            log.info("Running qualitative gate on %d candidates...", len(gate_candidates))
            candidates = _gate(scorer, gate_candidates)

            if not candidates:
                log.info("Gate filtered all candidates — no genuine editorial "
                         "inflation detected today.")
            else:
                log.info("%d article(s) passed the gate.", len(candidates))
                scored = _full_score(scorer, session, candidates)

            if len(scored) > 1:
                log.info("Asking judge to pick winner from %d candidates...", len(scored))
                winner_article, winner_result = _pick_winner(scorer, session, scored)
                log.info('Dashboard highlight: "%s"', (winner_article.title or "")[:70])
                log.info("ragebait=%.1f", winner_result.ragebait_score)
            elif scored:
                winner_article, winner_result = scored[0]
                log.info('Dashboard highlight (single candidate): "%s"',
                         (winner_article.title or "")[:70])
                log.info("ragebait=%.1f", winner_result.ragebait_score)

    log.info("Pipeline done.")
    return bool(scored)
