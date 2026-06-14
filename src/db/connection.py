"""
Database engine and session factory.
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base


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


def init_db() -> None:
    """Ensure all tables exist on the shared engine used by get_session()."""
    create_tables(_get_engine())


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
