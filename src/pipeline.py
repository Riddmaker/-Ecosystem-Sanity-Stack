"""
Core pipeline logic — importable function so it can be called from both
the CLI (run_pipeline.py) and the scheduler (scheduler.py).
"""

import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.db.connection import build_engine, create_tables, get_session
from src.db.repository import ArticleRepository
from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
    TwentyMinutesScraperConnector,
    DEFAULT_SECTIONS as TWENTYMIN_SECTIONS,
)
from src.connectors.specific_scraper.watson_scraper_connector import (
    WatsonScraperConnector,
    DEFAULT_SECTIONS as WATSON_SECTIONS,
)
from src.connectors.specific_scraper.blick_scraper_connector import (
    BlickScraperConnector,
    DEFAULT_SECTIONS as BLICK_SECTIONS,
)
from src.scoring.pre_scorer import PreScorer, pre_score_to_db_fields, PRE_SCORE_THRESHOLD
from src.scoring.scorer import MediaScorer, result_to_db_fields

ALL_SOURCES = ["20min", "watson", "blick"]


def run(
    hours: Optional[float] = None,
    max_articles: Optional[int] = None,
    sources: Optional[list[str]] = None,
) -> bool:
    """
    Run the full pipeline: scrape → upsert → pre-screen → full-score top 3.

    Args:
        hours:        Only include articles published within the last N hours.
        max_articles: Hard cap on articles fetched per source.
        sources:      Which sources to scrape. Defaults to all three.

    Returns:
        True if at least one article was fully scored, False otherwise.
    """
    if sources is None:
        sources = ALL_SOURCES

    build_engine()
    create_tables(build_engine())

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours) if hours else None

    print(f"\n[pipeline] {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if since:
        print(f"[pipeline] Filter: articles since {since.strftime('%H:%M UTC')} (--hours {hours})")
    if max_articles:
        print(f"[pipeline] Cap: max {max_articles} articles per source")
    print(f"[pipeline] Sources: {', '.join(sources)}")
    print("=" * 60)

    # ── 1. Scrape ────────────────────────────────────────────────
    print("\n[1/4] Scraping sources...")
    all_articles = []

    if "20min" in sources:
        print("      20min.ch")
        try:
            fetched = TwentyMinutesScraperConnector(sections=TWENTYMIN_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    if "watson" in sources:
        print("      watson.ch")
        try:
            fetched = WatsonScraperConnector(sections=WATSON_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    if "blick" in sources:
        print("      blick.ch")
        try:
            fetched = BlickScraperConnector(sections=BLICK_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    print(f"      Total: {len(all_articles)} articles across all sources")

    # ── 2. Upsert ────────────────────────────────────────────────
    print("\n[2/4] Upserting to DB...")
    with get_session() as session:
        repo = ArticleRepository(session)
        results = repo.upsert_many(all_articles)

    new_or_updated_urls = [url for url, changed in results.items() if changed]
    unchanged_urls      = [url for url, changed in results.items() if not changed]
    print(f"      {len(new_or_updated_urls)} new/updated   {len(unchanged_urls)} unchanged")

    # ── 3. Pre-screen ────────────────────────────────────────────
    print(f"\n[3/4] Pre-screening {len(new_or_updated_urls)} articles with Mistral Small...")

    if not new_or_updated_urls:
        print("      Nothing to pre-score.")
    else:
        pre_scorer = PreScorer()
        with get_session() as session:
            repo = ArticleRepository(session)
            to_prescreen = repo.get_unprescored(urls=new_or_updated_urls)

            flagged_count = 0
            for article in to_prescreen:
                try:
                    result = pre_scorer.score(
                        title=article.title or "", content=article.content or ""
                    )
                    fields = pre_score_to_db_fields(result)
                    for k, v in fields.items():
                        setattr(article, k, v)
                    session.flush()

                    flag = "FLAG" if result.score >= PRE_SCORE_THRESHOLD else "    "
                    if result.score >= PRE_SCORE_THRESHOLD:
                        flagged_count += 1
                    print(f"      [{flag}] {result.score:.1f}  {article.title[:60]}")
                except Exception as e:
                    print(f"      [ERR ] {article.title[:60]}: {e}")

        print(f"\n      {flagged_count} of {len(to_prescreen)} flagged (pre_score >= {PRE_SCORE_THRESHOLD})")

    # ── 4. Full-score top 3 ──────────────────────────────────────
    print("\n[4/4] Full-scoring top 3 candidates with Mistral Large...")

    fully_scored = False
    with get_session() as session:
        repo = ArticleRepository(session)
        candidates = repo.get_top_prescored_unscored(n=5)

        if not candidates:
            print("      No candidates found (all already scored or none above threshold).")
        else:
            scorer = MediaScorer()
            scored = []
            for candidate in candidates:
                print(f"      → pre_score={candidate.pre_score:.1f}  \"{candidate.title[:60]}\"")
                try:
                    result = scorer.score(
                        title=candidate.title or "", content=candidate.content or ""
                    )
                    fields = result_to_db_fields(result)
                    for k, v in fields.items():
                        setattr(candidate, k, v)
                    session.flush()
                    discrepancy = result.ragebait_score - result.emotional_weight
                    print(
                        f"         ragebait={result.ragebait_score:.1f}  "
                        f"weight={result.emotional_weight:.1f}  "
                        f"discrepancy={discrepancy:+.1f}"
                    )
                    scored.append((candidate, result, discrepancy))
                    fully_scored = True
                except Exception as e:
                    print(f"         ERROR: {e}")

            if scored:
                winner = max(scored, key=lambda x: x[2])
                print(f"\n      Dashboard highlight: \"{winner[0].title[:70]}\"")
                print(
                    f"      ragebait={winner[1].ragebait_score:.1f}  "
                    f"weight={winner[1].emotional_weight:.1f}  "
                    f"discrepancy={winner[2]:+.1f}"
                )

    print("\n[pipeline] Done.")
    print("=" * 60)
    return fully_scored
