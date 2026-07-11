"""Shared fixtures for paper trading tests."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_PG_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test"


def _postgres_url() -> str:
    return os.environ.get("PAPER_TRADING_DATABASE_URL", DEFAULT_PG_URL)


def postgres_available() -> bool:
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


requires_postgres = pytest.mark.postgres(
    pytest.mark.skipif(
        not postgres_available(),
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
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    yield engine
    command.downgrade(alembic_config, "base")
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
