"""Shared fixtures for paper trading tests."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

DEFAULT_PG_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test"


def _postgres_url() -> str:
    return os.environ.get("PAPER_TRADING_DATABASE_URL", DEFAULT_PG_URL)


def postgres_available() -> bool:
    if os.environ.get("PAPER_TRADING_DATABASE_URL") is None:
        return False
    try:
        engine = create_engine(
            _postgres_url(),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


_postgres_available_cache: bool | None = None


def _is_postgres_available() -> bool:
    global _postgres_available_cache
    if _postgres_available_cache is None:
        _postgres_available_cache = postgres_available()
    return _postgres_available_cache


requires_postgres = pytest.mark.postgres(
    pytest.mark.skipif(
        not _is_postgres_available(),
        reason="PostgreSQL not available at PAPER_TRADING_DATABASE_URL",
    )
)


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _postgres_url())
    return cfg


@pytest.fixture(scope="session")
def migrated_engine(alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    yield engine
    command.downgrade(alembic_config, "base")
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
