"""Production runner integration with fake market data runtime."""

from __future__ import annotations

import asyncio

import pytest
from paper_trading.application import FakeMarketDataRuntime, PaperTradingApplication
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.service_config import PaperServiceConfig
from sqlalchemy import text

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
    assert runtime.status == RuntimeStatus.READY
    assert not runtime.last_error
    assert app.advisory_lock.held is True
    assert app.market_data_ready() is True
    assert app._session_factory is not app._heartbeat_session_factory  # noqa: SLF001
    assert app._session_factory.kw["bind"] is not app._heartbeat_session_factory.kw[  # noqa: SLF001
        "bind"
    ]
    with app._session_factory() as scheduler_session:  # noqa: SLF001
        scheduler_identity = scheduler_session.execute(
            text("SELECT pg_backend_pid(), current_setting('application_name')")
        ).one()
    with app._heartbeat_session_factory() as heartbeat_session:  # noqa: SLF001
        heartbeat_identity = heartbeat_session.execute(
            text("SELECT pg_backend_pid(), current_setting('application_name')")
        ).one()
    assert scheduler_identity[0] != heartbeat_identity[0]
    assert scheduler_identity[1] == "paper-worker-scheduler"
    assert heartbeat_identity[1] == "paper-worker-heartbeat"

    app._update_runtime_readiness()  # noqa: SLF001
    assert app.repository.session.in_transaction() is False
    with migrated_engine.begin() as independent:
        independent.execute(text("SET LOCAL lock_timeout = '100ms'"))
        independent.execute(
            text(
                "UPDATE runtime_state SET heartbeat_at = heartbeat_at "
                "WHERE instance_id = '00000000-0000-0000-0000-000000000001'"
            )
        )

    secondary = PostgresAdvisoryLock(migrated_engine, config.advisory_lock_id)
    assert secondary.try_acquire() is False

    await app.stop()
    assert fake_md.closed is True
    assert app.advisory_lock.held is False
    assert app._heartbeat_engine is None  # noqa: SLF001

    assert secondary.try_acquire() is True
    secondary.release()


@pytest.mark.asyncio
async def test_second_runner_stays_passive_while_first_holds_lock(
    migrated_engine,
    alembic_config,
) -> None:
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        advisory_lock_startup_timeout_seconds=0.05,
    )
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


@pytest.mark.asyncio
async def test_rolling_successor_waits_for_advisory_lock_release(
    migrated_engine,
    alembic_config,
) -> None:
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        advisory_lock_startup_timeout_seconds=1.0,
    )
    first = PaperTradingApplication(
        config=config,
        market_data_runtime=FakeMarketDataRuntime(),
        alembic_config=alembic_config,
    )
    second = PaperTradingApplication(
        config=config,
        market_data_runtime=FakeMarketDataRuntime(),
        alembic_config=alembic_config,
    )
    await first.start()
    successor = asyncio.create_task(second.start())
    await asyncio.sleep(0.05)
    assert successor.done() is False

    await first.stop()
    await successor

    assert second.advisory_lock.held is True
    await second.stop()
