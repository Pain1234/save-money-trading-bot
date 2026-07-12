"""Full production lifecycle integration test (15 steps)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from paper_trading.clock import FixedClock
from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
from paper_trading.enums import (
    PaperFillKind,
    RuntimeStatus,
    SchedulerRunStatus,
    TradeIntentStatus,
)
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.market_events import MarketEventBridge
from paper_trading.orchestrator import PaperTradingOrchestrator
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.service_config import PaperServiceConfig
from paper_trading.symbol_constraints import StaticSymbolConstraintsProvider

from tests.paper_trading.bridge_test_helpers import poll_commit_ack
from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.e2e.helpers import build_breakout_historical_bundle
from tests.paper_trading.integration.lifecycle_helpers import (
    btc_eth_sol_constraints,
    eval_time_after_close,
    ingest_historical_bundle,
    next_day_open,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def _set_runtime_ready(repo: PaperTradingRepository) -> None:
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.READY,
        expected_version=runtime.version,
    )


def _build_bridge(
    repo: PaperTradingRepository,
    md: ControlledMarketDataRuntime,
    config: PaperServiceConfig,
    clock: FixedClock,
    lock: PostgresAdvisoryLock,
) -> MarketEventBridge:
    orchestrator = PaperTradingOrchestrator(repo, config, clock=clock)
    orchestrator.scheduler._market_data_ready = lambda: md.status(clock.now()).readiness  # noqa: SLF001
    orchestrator.scheduler.set_jobs_enabled(True)
    constraints = StaticSymbolConstraintsProvider(btc_eth_sol_constraints())
    context_builder = ProductionContextBuilder(
        market_data=md.service,
        repository=repo,
        config=config,
        constraints=constraints,
        clock=clock,
        market_data_ready=lambda: md.status(clock.now()).readiness,
    )
    return MarketEventBridge(
        repository=repo,
        candle_repository=md.repository,
        scheduler=orchestrator.scheduler,
        context_builder=context_builder,
        config=config,
        clock=clock,
        advisory_lock=lock,
        market_data_ready=lambda: md.status(clock.now()).readiness,
    )


@pytest.mark.asyncio
async def test_production_runner_full_lifecycle_fifteen_steps(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol = "BTC"
    bundle = build_breakout_historical_bundle(symbol, include_exit_candle=True)
    signal_candle = bundle.daily[symbol][-2]
    fill_candle = bundle.daily[symbol][-1]

    signal_eval_time = eval_time_after_close(signal_candle, delay_seconds=5)
    fill_eval_time = next_day_open(signal_candle) + timedelta(seconds=1)

    clock = FixedClock(signal_eval_time)
    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=signal_eval_time - timedelta(seconds=1),
    )
    await md.start(signal_eval_time)

    lock_id = 987655000 + (os.getpid() % 50000)
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        symbols=(symbol,),
        fill_delay_seconds=0,
        evaluation_delay_seconds=5,
        heartbeat_interval_seconds=3600,
        stale_runtime_threshold_seconds=7200,
        advisory_lock_id=lock_id,
    )

    repo = PaperTradingRepository(postgres_commit_session)
    lock = PostgresAdvisoryLock(migrated_engine, lock_id)
    assert lock.try_acquire() is True

    _set_runtime_ready(repo)
    bridge = _build_bridge(repo, md, config, clock, lock)

    md.enqueue_raw(
        raw_daily(
            symbol,
            signal_candle.open_time,
            open_=str(signal_candle.open),
            high=str(signal_candle.high),
            low=str(signal_candle.low),
            close=str(signal_candle.close),
            volume=str(signal_candle.volume),
            is_closed=True,
        )
    )
    await md.process_live(clock.now())
    poll = bridge.process_after_poll(clock.now())
    repo.session.commit()
    bridge.acknowledge_committed(poll.events_to_ack)
    assert any(o.status == SchedulerRunStatus.COMPLETED for o in poll.outcomes)
    assert len(repo.list_evaluations(limit=10)) >= 1

    intents = [i for i in repo.list_intents(limit=10) if i.status == TradeIntentStatus.SCHEDULED]
    assert len(intents) == 1
    intent = intents[0]
    assert intent.symbol == symbol
    assert not [
        f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY
    ]

    clock.advance_to(fill_eval_time)
    md.enqueue_raw(
        raw_daily(
            symbol,
            fill_candle.open_time,
            open_=str(fill_candle.open),
            high=str(fill_candle.high),
            low=str(fill_candle.low),
            close=str(fill_candle.close),
            volume=str(fill_candle.volume),
            is_closed=False,
        )
    )
    await md.process_live(clock.now())
    poll = poll_commit_ack(bridge, repo, clock.now())
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    assert len(repo.get_open_positions()) == 1

    position = repo.get_open_positions()[0]
    active_stop = position.current_stop
    clock.advance_to(fill_eval_time + timedelta(hours=6))
    above_stop_low = active_stop + Decimal("1000")
    md.enqueue_raw(
        raw_daily(
            symbol,
            fill_candle.open_time,
            open_=str(fill_candle.open),
            high=str(max(fill_candle.high, above_stop_low)),
            low=str(above_stop_low),
            close=str(max(fill_candle.close, above_stop_low)),
            volume=str(fill_candle.volume),
            is_closed=False,
        )
    )
    await md.process_live(clock.now())
    poll = poll_commit_ack(bridge, repo, clock.now())
    assert len(repo.get_open_positions()) == 1

    clock.advance_to(fill_eval_time + timedelta(hours=12))
    below_stop_low = active_stop - Decimal("1")
    md.enqueue_raw(
        raw_daily(
            symbol,
            fill_candle.open_time,
            open_=str(fill_candle.open),
            high=str(max(fill_candle.high, below_stop_low)),
            low=str(below_stop_low),
            close=str(below_stop_low),
            volume=str(fill_candle.volume),
            is_closed=False,
        )
    )
    await md.process_live(clock.now())
    poll = poll_commit_ack(bridge, repo, clock.now())
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.EXIT]) == 1
    assert not repo.get_open_positions()

    counts_before = {
        "fills": len(repo.list_fills(limit=100)),
        "intents": len(repo.list_intents(limit=100)),
    }

    lock.release()
    postgres_commit_session.commit()

    clock.advance_to(fill_eval_time + timedelta(days=1))
    md2 = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md2,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]),
        evaluation_time=clock.now(),
    )
    await md2.start(clock.now())
    lock2 = PostgresAdvisoryLock(migrated_engine, lock_id)
    assert lock2.try_acquire() is True
    repo2 = PaperTradingRepository(postgres_commit_session)
    _set_runtime_ready(repo2)
    bridge2 = _build_bridge(repo2, md2, config, clock, lock2)
    poll_commit_ack(bridge2, repo2, clock.now())

    assert len(repo2.list_fills(limit=100)) == counts_before["fills"]
    assert len(repo2.list_intents(limit=100)) == counts_before["intents"]

    secondary = PostgresAdvisoryLock(migrated_engine, lock_id)
    assert secondary.try_acquire() is False
    lock2.release()
    assert secondary.try_acquire() is True
    secondary.release()


@pytest.mark.asyncio
async def test_production_lifecycle_transient_open_context_retry(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """First poll with retryable missing open context, second poll completes entry fill."""
    from unittest.mock import patch

    from paper_trading.market_event_errors import RetryableContextNotReady

    symbol = "BTC"
    bundle = build_breakout_historical_bundle(symbol, include_exit_candle=True)
    signal_candle = bundle.daily[symbol][-2]
    fill_candle = bundle.daily[symbol][-1]

    signal_eval_time = eval_time_after_close(signal_candle, delay_seconds=5)
    fill_eval_time = next_day_open(signal_candle) + timedelta(seconds=1)

    clock = FixedClock(signal_eval_time)
    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=signal_eval_time - timedelta(seconds=1),
    )
    await md.start(signal_eval_time)

    lock_id = 987655500 + (os.getpid() % 50000)
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        symbols=(symbol,),
        fill_delay_seconds=0,
        evaluation_delay_seconds=5,
        heartbeat_interval_seconds=3600,
        stale_runtime_threshold_seconds=7200,
        advisory_lock_id=lock_id,
    )

    repo = PaperTradingRepository(postgres_commit_session)
    lock = PostgresAdvisoryLock(migrated_engine, lock_id)
    assert lock.try_acquire() is True
    _set_runtime_ready(repo)

    md.enqueue_raw(
        raw_daily(
            symbol,
            signal_candle.open_time,
            open_=str(signal_candle.open),
            high=str(signal_candle.high),
            low=str(signal_candle.low),
            close=str(signal_candle.close),
            volume=str(signal_candle.volume),
            is_closed=True,
        )
    )
    await md.process_live(clock.now())
    bridge = _build_bridge(repo, md, config, clock, lock)
    poll_commit_ack(bridge, repo, clock.now())
    assert len([i for i in repo.list_intents(limit=10) if i.status == TradeIntentStatus.SCHEDULED]) == 1

    clock.advance_to(fill_eval_time)
    md.enqueue_raw(
        raw_daily(
            symbol,
            fill_candle.open_time,
            open_=str(fill_candle.open),
            high=str(fill_candle.high),
            low=str(fill_candle.low),
            close=str(fill_candle.close),
            volume=str(fill_candle.volume),
            is_closed=False,
        )
    )
    await md.process_live(clock.now())

    real_build = ProductionContextBuilder.build_open_contexts
    call_count = {"n": 0}

    def flaky_build_open(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RetryableContextNotReady("atr14 not available for transient test")
        return real_build(self, *args, **kwargs)

    with patch.object(ProductionContextBuilder, "build_open_contexts", flaky_build_open):
        first = bridge.process_after_poll(clock.now())
        repo.session.commit()
        assert any(o.deferred for o in first.outcomes)
        assert not first.events_to_ack
        assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 0

        second = poll_commit_ack(bridge, repo, clock.now())
        assert any(o.status == SchedulerRunStatus.COMPLETED for o in second.outcomes)
        assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1

    lock.release()


@pytest.mark.asyncio
async def test_market_data_disconnect_sets_degraded(
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    clock = FixedClock(datetime(2024, 6, 1, tzinfo=UTC))
    md = ControlledMarketDataRuntime.create()
    lock_id = 987655000 + (os.getpid() % 50000) + 1
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        symbols=("BTC",),
        heartbeat_interval_seconds=3600,
        stale_runtime_threshold_seconds=7200,
        advisory_lock_id=lock_id,
    )
    repo = PaperTradingRepository(postgres_commit_session)
    lock = PostgresAdvisoryLock(__import__("sqlalchemy").create_engine(_postgres_url()), lock_id)
    assert lock.try_acquire()
    _set_runtime_ready(repo)
    bridge = _build_bridge(repo, md, config, clock, lock)
    md.set_connected(False)
    result = bridge.process_after_poll(clock.now())
    assert result.outcomes == ()
    lock.release()
