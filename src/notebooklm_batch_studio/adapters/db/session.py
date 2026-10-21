"""Engine and session helpers: one place that knows how to connect and how to commit.

`session_scope()` commits when the block succeeds and rolls back on any error, so a
failed request never leaves half-written data.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_db_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine.

    For SQLite files the parent folder is created; `sqlite://` (in memory) uses one shared
    connection so tests and the API see the same data.

    Args:
        database_url: e.g. `sqlite:////Volumes/drive/projects-data/app/db/app.db` or `postgresql+psycopg://user@127.0.0.1/db`.

    Returns:
        The engine.
    """
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        return create_engine(database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the session factory used by repositories.

    Args:
        engine: Engine from `create_db_engine()`.

    Returns:
        A `sessionmaker` that does not expire objects on commit.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Open a session, commit on success, roll back on error, always close.

    Args:
        factory: Session factory from `make_session_factory()`.

    Yields:
        An open session.

    Raises:
        Exception: Any error from the block is re-raised after rollback.
    """
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
