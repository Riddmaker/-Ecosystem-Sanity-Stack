"""
Database engine and session factory.
"""

import logging
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base

log = logging.getLogger(__name__)

# Idempotent column additions for tables that already exist in production.
# Base.metadata.create_all() creates *missing tables* but never ALTERs an
# existing one, so columns added to a model after the table was first created
# (e.g. the fact-check track) would never appear on the prod `articles` table.
# Each statement is ADD COLUMN IF NOT EXISTS, so running them on every startup
# is a no-op once applied. Postgres-only (guarded in run_migrations).
_MIGRATIONS: tuple[str, ...] = (
    # Fact-Check track (Irreführungs-Index) — mirror of the ragebait columns.
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fc_pre_score DOUBLE PRECISION",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fc_pre_reasoning TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fc_pre_model VARCHAR(100)",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fc_pre_at TIMESTAMPTZ",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fact_check_score DOUBLE PRECISION",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fact_check_details JSONB",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fact_check_model VARCHAR(100)",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fact_check_version VARCHAR(20)",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS fact_check_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_articles_fc_pre_score ON articles (fc_pre_score)",
    "CREATE INDEX IF NOT EXISTS ix_articles_fact_check_score ON articles (fact_check_score)",
)


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return url


def build_engine(database_url: str | None = None, **kwargs):
    url = database_url or get_database_url()
    # Resilience against stale pooled connections. The DB node restarts on
    # redeploys, cloudlet changes and maintenance; without this the pool hands
    # out a dead socket and the next query raises
    # "psycopg2.OperationalError: server closed the connection unexpectedly".
    # pool_pre_ping does a lightweight liveness check (SELECT 1) and transparently
    # replaces a dead connection; pool_recycle caps connection age so we don't sit
    # on a socket the server silently dropped. Callers can override via kwargs.
    kwargs.setdefault("pool_pre_ping", True)
    kwargs.setdefault("pool_recycle", 300)
    return create_engine(url, **kwargs)


def create_tables(engine) -> None:
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(engine)


def run_migrations(engine) -> None:
    """Apply idempotent ADD COLUMN / CREATE INDEX statements to existing tables.

    create_all() never ALTERs a table that already exists, so columns added to a
    model later (the fact-check track) need explicit migrations to land on the
    production `articles` table. Postgres-only — on other backends (SQLite tests)
    create_all() already builds the full current schema, so this is a no-op.
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for stmt in _MIGRATIONS:
            conn.execute(text(stmt))
    log.debug("DB migrations applied (%d statements)", len(_MIGRATIONS))


def init_db() -> None:
    """Ensure all tables exist and are up to date on the shared engine."""
    engine = _get_engine()
    create_tables(engine)
    run_migrations(engine)


# Module-level singletons — initialised on first use
_engine = None
_SessionFactory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def _get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Session:
    """Context manager that yields a session and handles commit/rollback."""
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
