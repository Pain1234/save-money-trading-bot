"""Production runner integration with fake market data runtime."""

from __future__ import annotations

import pytest
from paper_trading.application import FakeMarketDataRuntime, PaperTradingApplication
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.service_config import PaperServiceConfig

from tests.paper_trading.conftest import _postgres_url, requires_postgres

pytestmark = [requires_postgres, pytest.mark.postgres]


@pytest.mark.asyncio
async def test_runner_startup_shutdown_with_fake_market_data(
    migrated_engine,
    alembic_config,
) -> None:
    config = PaperServiceConfig.from_env(database_url=_postgres_url())
    fake_md = FakeMarketDataRuntime()
    app = PaperTradingApplication(
        config=config,
        market_data_runtime=fake_md,
        alembic_config=alembic_config,
    )
    await app.start()
    runtime = app.repository.get_runtime_state()
    assert runtime is not None
    assert runtime.status in {RuntimeStatus.READY, RuntimeStatus.DEGRADED}
    assert app.advisory_lock.held is True
    assert app.market_data_ready() is True

    secondary = PostgresAdvisoryLock(migrated_engine, config.advisory_lock_id)
    assert secondary.try_acquire() is False

    await app.stop()
    assert fake_md.closed is True
    assert app.advisory_lock.held is False

    assert secondary.try_acquire() is True
    secondary.release()


@pytest.mark.asyncio
async def test_second_runner_stays_passive_while_first_holds_lock(
    migrated_engine,
    alembic_config,
) -> None:
    config = PaperServiceConfig.from_env(database_url=_postgres_url())
    first = PaperTradingApplication(
        config=config,
        market_data_runtime=FakeMarketDataRuntime(),
        alembic_config=alembic_config,
    )
    await first.start()
    second = PaperTradingApplication(
        config=config,
        market_data_runtime=FakeMarketDataRuntime(),
        alembic_config=alembic_config,
    )
    with pytest.raises(RuntimeError, match="advisory lock"):
        await second.start()
    await first.stop()
