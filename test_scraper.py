import os
from dotenv import load_dotenv

load_dotenv()

from src.db.connection import build_engine, create_tables, get_session
from src.db.repository import ArticleRepository
from src.connectors.specific_scraper.twenty_minutes_scraper_connector import TwentyMinutesScraperConnector

# 1. Ensure tables exist
engine = build_engine()
create_tables(engine)
print("DB tables ready.\n")

# 2. Scrape
connector = TwentyMinutesScraperConnector(sections=["/"])
articles = connector.get_articles(max_articles=5)

# 3. Upsert into DB
with get_session() as session:
    repo = ArticleRepository(session)
    results = repo.upsert_many(articles)

print(f"\n{'='*60}")
print(f"Upserted {len(results)} articles:")
for url, changed in results.items():
    status = "NEW/UPDATED" if changed else "unchanged"
    print(f"  [{status}] {url}")
