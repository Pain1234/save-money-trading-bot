"""Optional bounded live public Hyperliquid testnet soak."""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_public_data_soak() -> None:
    if os.environ.get("RUN_PAPER_LIVE_SOAK", "0") != "1":
        pytest.skip("RUN_PAPER_LIVE_SOAK not enabled")
    if os.environ.get("HYPERLIQUID_NETWORK", "") != "testnet":
        pytest.skip("HYPERLIQUID_NETWORK must be testnet")

    soak_seconds = int(os.environ.get("PAPER_LIVE_SOAK_SECONDS", "300"))
    assert soak_seconds >= 300
    max_seconds = min(soak_seconds, 600)

    from alembic.config import Config
    from market_data.models import ConnectionStatus, DataQualityStatus, MarketTimeframe
    from market_data.runtime import HyperliquidMarketDataRuntime
    from paper_trading.application import PaperTradingApplication
    from paper_trading.enums import RuntimeStatus, SchedulerRunStatus
    from paper_trading.lock import PostgresAdvisoryLock
    from paper_trading.scheduler import SchedulerJobName
    from paper_trading.service_config import PaperServiceConfig
    from paper_trading.soak_window import (
        complete_soak_run,
        create_soak_run,
        list_failed_market_event_runs_for_soak,
        unexpected_failed_market_event_runs,
    )

    from scripts.verify_paper_state import verify

    db_url = os.environ.get("PAPER_TRADING_DATABASE_URL")
    if not db_url:
        pytest.skip("PAPER_TRADING_DATABASE_URL required for live soak")

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    alembic_cfg = Config(os.path.join(root, "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    from alembic import command

    command.upgrade(alembic_cfg, "head")

    prep_engine = create_engine(db_url, pool_pre_ping=True)
    soak_run_id = create_soak_run(prep_engine)
    try:
        with prep_engine.connect() as conn:
            db_name = conn.execute(text("SELECT current_database()")).scalar_one()
            if db_name != "paper_trading_test":
                pytest.skip("live soak prep requires paper_trading_test database")
            conn.execute(
                text(
                    "UPDATE runtime_state SET status = 'STOPPED' "
                    "WHERE status IN ('DEGRADED', 'SHUTTING_DOWN')"
                )
            )
            conn.commit()
    finally:
        prep_engine.dispose()

    config = PaperServiceConfig.from_env(database_url=db_url)
    app = PaperTradingApplication(
        config=config,
        alembic_config=alembic_cfg,
        active_soak_run_id=soak_run_id,
    )
    md_runtime: HyperliquidMarketDataRuntime | None = None
    started_at = time.monotonic()

    await app.start()
    try:
        assert isinstance(app._md_runtime, HyperliquidMarketDataRuntime)
        md_runtime = app._md_runtime

        await asyncio.sleep(5)
        status = md_runtime.status(app.clock.now())
        assert md_runtime.meta_loaded is True
        assert status.http_status == "ready"
        assert md_runtime.backfill_complete is True
        assert status.websocket_status == ConnectionStatus.CONNECTED
        assert status.subscriptions_expected == 9
        assert status.subscriptions_acknowledged == 9

        symbols_seen = set()
        timeframes_seen = set()
        for series in status.series:
            symbols_seen.add(series.symbol.value)
            timeframes_seen.add(series.timeframe)
            assert series.quality_status == DataQualityStatus.VALID
        assert symbols_seen == {"BTC", "ETH", "SOL"}
        assert timeframes_seen == {
            MarketTimeframe.DAILY,
            MarketTimeframe.WEEKLY,
            MarketTimeframe.MONTHLY,
        }

        assert app.market_data_ready() is True
        runtime = app.repository.get_runtime_state()
        assert runtime is not None
        assert runtime.status in {RuntimeStatus.READY, RuntimeStatus.DEGRADED}

        await asyncio.sleep(max_seconds - 5)

        elapsed = time.monotonic() - started_at
        assert elapsed >= 300
        assert elapsed <= 420

        runtime = app.repository.get_runtime_state()
        assert runtime is not None
        assert runtime.status in {RuntimeStatus.READY, RuntimeStatus.DEGRADED}
        assert app.market_data_ready() is True

        heartbeat_runs = [
            run
            for run in app.repository.list_scheduler_runs(limit=500)
            if run.job_name == SchedulerJobName.RUNTIME_HEARTBEAT.value
            and run.status == SchedulerRunStatus.COMPLETED
        ]
        assert len(heartbeat_runs) >= 3

        orphans = app.repository.get_running_scheduler_runs()
        assert orphans == ()
    finally:
        await app.stop()

    assert app.is_started is False
    assert app.background_tasks == ()
    assert app.database_engine is None
    assert md_runtime is not None
    assert md_runtime.is_shutdown is True
    assert md_runtime.http_closed is True
    assert md_runtime.websocket_disconnected is True

    verify_engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with verify_engine.connect() as conn:
            running = conn.execute(
                text("SELECT COUNT(*) FROM scheduler_runs WHERE status = 'RUNNING'")
            ).scalar_one()
            failed_market_events = list_failed_market_event_runs_for_soak(
                conn,
                soak_run_id=soak_run_id,
            )
        assert running == 0

        allowed_failed_market_events: set[tuple[str, str | None]] = set()
        unexpected_failed = unexpected_failed_market_event_runs(
            failed_market_events,
            allowed=allowed_failed_market_events,
        )
        assert not unexpected_failed, (
            "unexpected FAILED market event scheduler runs in current soak window: "
            f"{unexpected_failed!r}"
        )
        for _job_name, error in failed_market_events:
            assert error is None or "missing open context" not in error.lower()

        complete_soak_run(verify_engine, soak_run_id)

        lock = PostgresAdvisoryLock(verify_engine, config.advisory_lock_id)
        assert lock.try_acquire()
        lock.release()
    finally:
        verify_engine.dispose()

    verify_result = verify(db_url)
    assert verify_result["ok"] is True
