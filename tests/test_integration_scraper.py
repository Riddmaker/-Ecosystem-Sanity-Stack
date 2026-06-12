"""
Integration tests for the scraper pipeline — requires a live DB.

What these tests verify:
  1. TwentyMinutesScraperConnector can fetch real articles from 20min.ch
  2. Articles are upserted to the DB correctly
  3. Re-upserting the same articles marks them as unchanged (dedup works)

Run:
  pytest tests/test_integration_scraper.py -m integration -v
"""

import pytest
from conftest import skip_no_db


@pytest.mark.integration
@skip_no_db
class TestScraperIntegration:

    def test_fetches_articles(self):
        """Scraper returns at least one article for the homepage."""
        from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
            TwentyMinutesScraperConnector,
        )

        connector = TwentyMinutesScraperConnector(sections=["/"])
        articles = connector.get_articles(max_articles=5)

        assert len(articles) > 0, "Expected at least one article from 20min.ch"
        assert all(a.title for a in articles), "All articles must have a title"
        assert all(a.url for a in articles), "All articles must have a URL"
        assert all(a.content for a in articles), "All articles must have content"

    def test_upsert_creates_new_records(self, db_session):
        """Freshly scraped articles are inserted into the DB."""
        from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
            TwentyMinutesScraperConnector,
        )
        from src.db.repository import ArticleRepository

        connector = TwentyMinutesScraperConnector(sections=["/"])
        articles = connector.get_articles(max_articles=3)

        repo = ArticleRepository(db_session)
        results = repo.upsert_many(articles)

        assert len(results) > 0

    def test_upsert_dedup_on_rerun(self, db_session):
        """Re-upserting the same articles marks them as unchanged (no re-scoring)."""
        from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
            TwentyMinutesScraperConnector,
        )
        from src.db.repository import ArticleRepository

        connector = TwentyMinutesScraperConnector(sections=["/"])
        articles = connector.get_articles(max_articles=3)

        repo = ArticleRepository(db_session)
        # First insert
        repo.upsert_many(articles)
        # Second insert — same articles, all should be unchanged
        results = repo.upsert_many(articles)

        unchanged = [url for url, changed in results.items() if not changed]
        assert len(unchanged) > 0, "Expected at least one unchanged article on re-upsert"

    def test_article_has_required_fields(self):
        """Parsed articles carry all mandatory fields for DB storage."""
        from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
            TwentyMinutesScraperConnector,
        )

        connector = TwentyMinutesScraperConnector(sections=["/"])
        articles = connector.get_articles(max_articles=2)

        for article in articles:
            assert article.source == "20min.ch"
            assert article.url.startswith("https://")
            assert article.published_at is not None
