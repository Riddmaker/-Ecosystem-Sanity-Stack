"""
Core pipeline logic — importable function so it can be called from both
the CLI (run_pipeline.py) and the scheduler (scheduler.py).

Stages: scrape → upsert → pre-screen → gate → full-score → judge.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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
from src.factcheck.pre_flag import FactCheckPreFlagger, fc_pre_flag_to_db_fields
from src.factcheck.claims import ClaimExtractor
from src.factcheck.retrieval import (
    GoogleFactCheckClient, TavilyClient, gather_claim_evidence, domain_of,
)
from src.factcheck.scorer import FactCheckScorer, fact_check_to_db_fields, FC_SCORE_VERSION
from src.factcheck.schemas import FactCheckResult

log = logging.getLogger(__name__)

CONNECTORS = {
    "20min":  TwentyMinutesScraperConnector,
    "watson": WatsonScraperConnector,
    "blick":  BlickScraperConnector,
    "nau":    NauScraperConnector,
}
# Every registered source — usable explicitly (e.g. CLI `--sources blick`).
ALL_SOURCES = list(CONNECTORS)
# Sources a default run actually scrapes (see config.DISABLED_SOURCES).
DEFAULT_SOURCES = [s for s in ALL_SOURCES if s not in config.DISABLED_SOURCES]


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
    """
    Run every requested connector; neither a failing nor a hanging source
    aborts the run. Each connector runs under a hard wall-clock cap
    (config.SCRAPE_SOURCE_TIMEOUT): if it overruns — e.g. a Playwright
    navigation that ignores its own timeout against a bot wall — the worker
    thread is abandoned and the run moves on to the next source.
    """
    all_articles: list[Article] = []
    for name in sources:
        connector_cls = CONNECTORS[name]
        log.info("Scraping %s", connector_cls.SOURCE)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"scrape-{name}")
        future = executor.submit(
            connector_cls().get_articles, since=since, max_articles=max_articles
        )
        try:
            fetched = future.result(timeout=config.SCRAPE_SOURCE_TIMEOUT)
            all_articles.extend(fetched)
            log.info("%s: %d articles", connector_cls.SOURCE, len(fetched))
        except FutureTimeoutError:
            log.error(
                "Scrape for %s exceeded %ss — skipping (worker thread abandoned).",
                connector_cls.SOURCE, config.SCRAPE_SOURCE_TIMEOUT,
            )
        except Exception:
            log.exception("Scrape failed for %s", connector_cls.SOURCE)
        finally:
            # Don't block on a stuck worker; let it die with the process.
            executor.shutdown(wait=False)
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


def _fc_prescreen(new_or_updated_urls: list[str]) -> None:
    """
    Fact-check Tier 1: pre-flag suspicion of unverified/unchecked claims with
    Mistral Small. Mirrors _prescreen but writes the fc_* columns and reads the
    fact-check work queue. Only invoked when config.FACTCHECK_ENABLED is set.
    """
    flagger = FactCheckPreFlagger()
    with get_session() as session:
        repo = ArticleRepository(session)
        for article in repo.get_fc_unflagged(urls=new_or_updated_urls):
            if is_paywalled(article):
                # Mark as flagged so it doesn't requeue every run
                article.fc_pre_score = 0.0
                article.fc_pre_reasoning = "SKIP: paywalled or teaser-only content"
                article.fc_pre_model = "none"
                article.fc_pre_at = datetime.now(timezone.utc)
                session.flush()
                log.info("[fc][paywall] %s", (article.title or "")[:60])
                continue

            try:
                result = flagger.flag(
                    title=article.title or "", content=article.content or ""
                )
                for k, v in fc_pre_flag_to_db_fields(result).items():
                    setattr(article, k, v)
                session.flush()
                log.info("[fc] %.1f  %s", result.score, (article.title or "")[:60])
            except Exception:
                log.exception("[fc] Pre-flag failed: %s", (article.title or "")[:60])


def _factcheck_due() -> bool:
    """
    Throttle the fact-check track to ~every config.FACTCHECK_EVERY_N_RUNS hours.
    Stateless across the per-hour subprocess runs: it reads the newest
    fact_check_at instead of an in-process counter, so winner-only Tavily stays
    inside the free tier even though each run is a fresh process.
    """
    n = config.FACTCHECK_EVERY_N_RUNS
    if n <= 1:
        return True
    with get_session() as session:
        latest = ArticleRepository(session).latest_fact_check_at()
    if latest is None:
        return True
    elapsed_h = (datetime.now(timezone.utc) - latest).total_seconds() / 3600.0
    return elapsed_h >= (n - 0.5)   # 0.5h slack for a slightly-late :00 run


def _fc_factcheck() -> Optional[tuple[ArticleModel, FactCheckResult]]:
    """
    Fact-check Tier 2 (winner-only). Pick the single most illustrative suspicious
    article, retrieve evidence for its claims (Google FCT free → Tavily only here),
    score it with three Mistral-Large sub-scores, and persist the verdict.
    """
    fct       = GoogleFactCheckClient()
    tavily    = TavilyClient()
    extractor = ClaimExtractor()
    scorer    = FactCheckScorer()

    with get_session() as session:
        repo = ArticleRepository(session)
        candidates = repo.get_fc_suspicious_above_threshold(
            min_score=config.FACTCHECK_SUSPICION_THRESHOLD,
            limit=config.FACTCHECK_CANDIDATE_LIMIT,
        )
        if not candidates:
            log.info("[FC] No suspicious candidates above threshold.")
            return None

        # Free FCT first pass on each candidate's title → cheap selection signal.
        judge_input = []
        for c in candidates:
            reviews = fct.search(c.title or "")
            judge_input.append({
                "title":            c.title or "",
                "fc_pre_score":     c.fc_pre_score or 0.0,
                "fc_pre_reasoning": c.fc_pre_reasoning or "",
                "fact_check_hits":  [r.rating for r in reviews if r.rating],
            })

        if len(candidates) == 1:
            idx, judge_reasoning = 0, "single candidate"
        else:
            verdict = scorer.judge_candidates(judge_input)
            idx, judge_reasoning = verdict["chosen"] - 1, verdict["reasoning"]
        winner = candidates[idx]
        log.info('[FC] Winner: "%s" (suspicion=%.1f)',
                 (winner.title or "")[:60], winner.fc_pre_score or 0.0)

        # Winner-only: extract claims, then retrieve evidence (Tavily here only).
        claims = extractor.extract(title=winner.title or "", content=winner.content or "")
        if not claims:
            log.info("[FC] No checkable claims for winner — marking processed.")
            winner.fact_check_score = 0.0
            winner.fact_check_details = {"skipped": "no checkable claims extracted"}
            winner.fact_check_model = "none"
            winner.fact_check_version = FC_SCORE_VERSION
            winner.fact_check_at = datetime.now(timezone.utc)
            session.flush()
            return None

        evidence = gather_claim_evidence(
            claims, fct, tavily,
            exclude_domains=[domain_of(winner.url)] if winner.url else None,
        )

        result = scorer.score(
            title=winner.title or "", content=winner.content or "",
            claims=claims, evidence=evidence,
        )
        for k, v in fact_check_to_db_fields(result, judge_reasoning).items():
            setattr(winner, k, v)
        session.flush()
        log.info("[FC] Irreführungs-Index=%.1f (accuracy=%s, framing=%.1f, context=%.1f)",
                 result.fact_check_score, result.fact_check.factual_accuracy_label,
                 result.fact_check.misleading_framing, result.fact_check.missing_context)
        return winner, result


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
        sources:      Which sources to scrape. Defaults to DEFAULT_SOURCES
                      (all registered sources minus config.DISABLED_SOURCES).

    Returns:
        True if at least one article was fully scored, False otherwise.
    """
    if sources is None:
        sources = DEFAULT_SOURCES

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

    # ── 3b. Fact-check pre-flag (optional second track) ──────────
    # Reuses the same scraped/upserted articles. Off by default
    # (config.FACTCHECK_ENABLED) so the ragebait pipeline is unchanged.
    if config.FACTCHECK_ENABLED and new_or_updated_urls:
        log.info("[FC] Pre-flagging %d articles for fact-check suspicion (Mistral Small)...",
                 len(new_or_updated_urls))
        _fc_prescreen(new_or_updated_urls)

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

    # ── 5. Fact-check verdict (optional, winner-only, throttled) ──
    # Off by default (config.FACTCHECK_ENABLED) and rate-limited to ~every
    # FACTCHECK_EVERY_N_RUNS hours so winner-only Tavily stays in the free tier.
    if config.FACTCHECK_ENABLED:
        if _factcheck_due():
            log.info("[FC] Running fact-check verdict (winner-only)...")
            _fc_factcheck()
        else:
            log.info("[FC] Skipping fact-check this run (cadence: every %dh).",
                     config.FACTCHECK_EVERY_N_RUNS)

    log.info("Pipeline done.")
    return bool(scored)
