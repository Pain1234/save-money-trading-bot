"""Database session factory for paper trading."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(
    database_url: str,
    *,
    echo: bool = False,
    application_name: str | None = None,
) -> Engine:
    """Create a SQLAlchemy engine for PostgreSQL."""
    connect_args = {"application_name": application_name} if application_name else {}
    return create_engine(
        database_url,
        echo=echo,
        future=True,
        connect_args=connect_args,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the engine."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a transactional scope without auto-commit (explicit begin required)."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
