"""PostgreSQL advisory lock integration tests."""

from __future__ import annotations

from paper_trading.config import PaperTradingConfig
from paper_trading.lock import PostgresAdvisoryLock
from sqlalchemy import create_engine

from tests.paper_trading.conftest import _postgres_url, requires_postgres


@requires_postgres
def test_advisory_lock_second_process_blocked(migrated_engine) -> None:
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    engine = create_engine(_postgres_url())
    lock_a = PostgresAdvisoryLock(engine, config.advisory_lock_id)
    lock_b = PostgresAdvisoryLock(engine, config.advisory_lock_id)
    try:
        assert lock_a.try_acquire() is True
        assert lock_a._connection is not None  # noqa: SLF001
        assert lock_a._connection.in_transaction() is False  # noqa: SLF001
        assert lock_b.try_acquire() is False
    finally:
        lock_a.release()
        lock_b.release()
        engine.dispose()


@requires_postgres
def test_advisory_lock_release_twice_safe(migrated_engine) -> None:
    engine = create_engine(_postgres_url())
    lock = PostgresAdvisoryLock(engine, 987654321)
    try:
        assert lock.try_acquire() is True
        lock.release()
        lock.release()
        assert lock.held is False
    finally:
        engine.dispose()
