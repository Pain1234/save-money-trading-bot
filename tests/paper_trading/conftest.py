"""Shared fixtures for paper trading tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from tests.postgres_fixtures import (  # noqa: F401 — re-exported for test imports
    _PAPER_TRADING_RESET_TABLES,
    ALLOWED_POSTGRES_TEST_DATABASE,
    DEFAULT_PG_URL,
    _postgres_url,
    _reset_postgres_market_data_state,
    _reset_postgres_trading_state,
    alembic_config,
    assert_postgres_test_database_safe,
    clean_production_db,
    db_session,
    migrated_engine,
    postgres_available,
    postgres_commit_session,
    postgres_runtime_writable,
    requires_postgres,
)


@pytest.fixture(autouse=True)
def _reset_inmemory_lock() -> Iterator[None]:
    from paper_trading.app_state import reset_app_state
    from paper_trading.lock import InMemoryAdvisoryLock

    reset_app_state()
    InMemoryAdvisoryLock.reset()
    yield
    reset_app_state()
    InMemoryAdvisoryLock.reset()


@pytest.fixture
def e2e_harness(request: pytest.FixtureRequest):
    from paper_trading.repository import PaperTradingRepository

    from tests.paper_trading.e2e.helpers import PaperE2EHarness, paper_config_from_env

    session: Session = request.getfixturevalue("db_session")
    harness = PaperE2EHarness(
        PaperTradingRepository(session),
        paper_config_from_env(_postgres_url()),
    )
    harness.set_runtime_ready()
    return harness
