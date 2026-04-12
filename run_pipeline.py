"""
Hourly pipeline: scrape → pre-screen → full-score top candidate.

Flow:
  1. Scrape all sections of 20min.ch
  2. Upsert all articles to DB
  3. Pre-score ALL new/updated articles with Mistral Small (title + 500 chars)
  4. Full-score the article with the highest pre_score using Mistral Large
  5. That article becomes the dashboard highlight

Cost model:
  - ~30 articles/hour × Mistral Small = cheap
  - 1 article/hour × Mistral Large (2 queries) = expensive calls only where it matters

Run manually:
  .venv/Scripts/python run_pipeline.py

Or schedule with Windows Task Scheduler / cron.
"""

from dotenv import load_dotenv
load_dotenv()

import sys
from datetime import datetime, timezone

from src.db.connection import build_engine, create_tables, get_session
from src.db.models import ArticleModel
from src.db.repository import ArticleRepository
from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
    TwentyMinutesScraperConnector,
    DEFAULT_SECTIONS,
)
from src.scoring.pre_scorer import PreScorer, pre_score_to_db_fields, PRE_SCORE_THRESHOLD
from src.scoring.scorer import MediaScorer, result_to_db_fields

engine = build_engine()
create_tables(engine)

now = datetime.now(timezone.utc)
print(f"\n[pipeline] {now.strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 60)


# ── 1. Scrape ────────────────────────────────────────────────
print("\n[1/4] Scraping 20min.ch...")
connector = TwentyMinutesScraperConnector(sections=DEFAULT_SECTIONS)
articles = connector.get_articles()
print(f"      {len(articles)} articles fetched")


# ── 2. Upsert ────────────────────────────────────────────────
print("\n[2/4] Upserting to DB...")
with get_session() as session:
    repo = ArticleRepository(session)
    results = repo.upsert_many(articles)

new_or_updated_urls = [url for url, changed in results.items() if changed]
unchanged_urls      = [url for url, changed in results.items() if not changed]
print(f"      {len(new_or_updated_urls)} new/updated   {len(unchanged_urls)} unchanged")


# ── 3. Pre-score new articles ────────────────────────────────
print(f"\n[3/4] Pre-screening {len(new_or_updated_urls)} articles with Mistral Small...")

if not new_or_updated_urls:
    print("      Nothing to pre-score.")
else:
    pre_scorer = PreScorer()
    with get_session() as session:
        repo = ArticleRepository(session)
        to_prescreeen = repo.get_unprescored(urls=new_or_updated_urls)

        flagged_count = 0
        for article in to_prescreeen:
            try:
                result = pre_scorer.score(title=article.title or "", content=article.content or "")
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

    print(f"\n      {flagged_count} of {len(to_prescreeen)} flagged (pre_score >= {PRE_SCORE_THRESHOLD})")


# ── 4. Full-score the top candidate ─────────────────────────
print("\n[4/4] Full-scoring top candidate with Mistral Large...")

with get_session() as session:
    repo = ArticleRepository(session)
    top = repo.get_top_prescored_unscored()

    if not top:
        print("      No candidate found (all already scored or no articles above threshold).")
    else:
        print(f"      Candidate: pre_score={top.pre_score:.1f}  \"{top.title[:60]}\"")
        try:
            scorer = MediaScorer()
            result = scorer.score(title=top.title or "", content=top.content or "")
            fields = result_to_db_fields(result)
            for k, v in fields.items():
                setattr(top, k, v)
            session.flush()
            print(f"      ragebait={result.ragebait_score:.1f}  weight={result.emotional_weight:.1f}")
        except Exception as e:
            print(f"      ERROR during full scoring: {e}")
            sys.exit(1)

print("\n[pipeline] Done.")
print("=" * 60)
