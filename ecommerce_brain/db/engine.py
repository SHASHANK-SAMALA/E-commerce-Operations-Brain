"""DB engine + session management (SQLAlchemy 2.x async-compatible sync sessions)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ecommerce_brain.config.settings import settings


def _normalize_db_url(url: str) -> str:
    # Force the psycopg3 driver — psycopg2 is not in our dependency set.
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_db_url = _normalize_db_url(settings.database_url)
_is_sqlite = _db_url.startswith("sqlite")

_engine_kwargs: dict = {"pool_pre_ping": True}
if not _is_sqlite:
    _engine_kwargs.update(
        pool_size=5,
        max_overflow=10,
        connect_args={"options": "-c search_path=public"},
    )

engine = create_engine(_db_url, **_engine_kwargs)


# Enable pgvector extension on first connect (Postgres only — SQLite has no extensions)
if not _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_pgvector(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        dbapi_connection.commit()
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def initialize_database() -> None:
    """Import ORM models and create any missing tables."""
    from ecommerce_brain.db import models  # noqa: F401

    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
