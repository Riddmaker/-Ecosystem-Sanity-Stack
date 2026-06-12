"""
Shared pytest fixtures and markers.

Markers:
  integration  — requires a live DB and/or Mistral API key.
                 Skipped automatically unless both are available.

Usage:
  pytest tests/                          # unit tests only
  pytest tests/ -m integration           # integration tests only (needs .env)
  pytest tests/ -m "not integration"     # explicitly skip integration
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires a live PostgreSQL DB and MISTRAL_API_KEY",
    )


# ── Shared skip conditions ────────────────────────────────────────────────────

def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _mistral_key() -> str | None:
    return os.environ.get("MISTRAL_API_KEY")


skip_no_db = pytest.mark.skipif(
    not _db_url(),
    reason="DATABASE_URL not set — skipping DB integration test",
)

skip_no_api_key = pytest.mark.skipif(
    not _mistral_key(),
    reason="MISTRAL_API_KEY not set — skipping scoring integration test",
)


# ── DB session fixture ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_session():
    """Live DB session — only used by integration tests."""
    from src.db.connection import build_engine, create_tables, get_session

    engine = build_engine()
    create_tables(engine)

    with get_session() as session:
        yield session


# ── Scorer fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def pre_scorer():
    from src.scoring.pre_scorer import PreScorer
    return PreScorer()


@pytest.fixture(scope="session")
def media_scorer():
    from src.scoring.scorer import MediaScorer
    return MediaScorer()
