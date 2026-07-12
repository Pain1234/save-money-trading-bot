"""PostgreSQL regression tests for atomic daily open and recovery attempt history."""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from paper_trading.application import PaperTradingApplication
from paper_trading.clock import FixedClock
from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
from paper_trading.enums import PaperFillKind, SchedulerRunStatus
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.market_event_errors import RetryableContextNotReady
from paper_trading.market_events import (
    MarketEvent,
    MarketEventBridge,
    MarketEventType,
    daily_open_fill_job_name,
    daily_open_gap_job_name,
    daily_open_snapshot_job_name,
    market_event_job_name,
)
from paper_trading.service_config import PaperServiceConfig
from sqlalchemy.orm import sessionmaker

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.e2e.helpers import build_breakout_historical_bundle
from tests.paper_trading.integration.lifecycle_helpers import (
    eval_time_after_close,
    ingest_historical_bundle,
    next_day_open,
)
from tests.paper_trading.integration.test_production_lifecycle_full import (
    _build_bridge,
    _set_runtime_ready,
)
from tests.paper_trading.test_lifecycle_failure_recovery_integrity import (
    _application_poll,
    _commit_and_ack,
    _poll,
)
from tests.paper_trading.test_permanent_configuration_failures import (
    _context_builder,
    _valid_constraints,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


async def _prepare_open_poll(
    *,
    lock_id_offset: int,
    postgres_commit_session,
    migrated_engine,
):
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

    lock_id = lock_id_offset + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository

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
    assert lock.try_acquire()
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
    _commit_and_ack(bridge, repo, _poll(bridge, clock.now()))

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

    return symbol, md, config, clock, lock, bridge, repo, fill_candle


def _fresh_repo(migrated_engine):
    from paper_trading.repository import PaperTradingRepository

    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    return PaperTradingRepository(session), session


@pytest.mark.asyncio
async def test_atomic_open_snapshot_failure_rolls_back_economic_effects(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol, _md, config, clock, lock, bridge, repo, fill_candle = await _prepare_open_poll(
        lock_id_offset=987660000,
        postgres_commit_session=postgres_commit_session,
        migrated_engine=migrated_engine,
    )

    wallet_before = repo.get_wallet()
    assert wallet_before is not None
    cash_before = wallet_before.cash

    parent = market_event_job_name(
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol=symbol,
            candle_open_time=fill_candle.open_time,
            provider_received_at=clock.now(),
        )
    )
    gap_job = daily_open_gap_job_name(symbol, fill_candle.open_time)
    fill_job = daily_open_fill_job_name(symbol, fill_candle.open_time)
    snap_job = daily_open_snapshot_job_name(symbol, fill_candle.open_time)

    real_snapshot = bridge.scheduler.run_daily_open_snapshot
    bridge.scheduler.run_daily_open_snapshot = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("snapshot failed after fill")
    )

    app = PaperTradingApplication(config=config)
    app._repo = repo
    app._event_bridge = bridge
    _application_poll(app, clock.now())

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        assert not [
            f for f in fresh_repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY
        ]
        assert not fresh_repo.get_open_positions()
        wallet_after = fresh_repo.get_wallet()
        assert wallet_after is not None
        assert wallet_after.cash == cash_before

        parent_run = fresh_repo.get_scheduler_run(parent, fill_candle.open_time)
        assert parent_run is not None
        assert parent_run.status == SchedulerRunStatus.FAILED

        gap_run = fresh_repo.get_scheduler_run(gap_job, fill_candle.open_time)
        fill_run = fresh_repo.get_scheduler_run(fill_job, fill_candle.open_time)
        snap_run = fresh_repo.get_scheduler_run(snap_job, fill_candle.open_time)
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        assert fill_run is None or fill_run.status != SchedulerRunStatus.COMPLETED
        assert snap_run is not None and snap_run.status == SchedulerRunStatus.FAILED
        assert not fresh_repo.get_running_scheduler_runs()
    finally:
        fresh_session.close()

    bridge.scheduler.run_daily_open_snapshot = real_snapshot  # type: ignore[method-assign]
    _application_poll(app, clock.now())
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    lock.release()


@pytest.mark.asyncio
async def test_atomic_open_fill_failure_rolls_back_after_successful_gap(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol, _md, _config, clock, lock, bridge, repo, fill_candle = await _prepare_open_poll(
        lock_id_offset=987660100,
        postgres_commit_session=postgres_commit_session,
        migrated_engine=migrated_engine,
    )

    bridge.scheduler.run_daily_open_fill = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("fill failed after gap")
    )

    app = PaperTradingApplication(config=_config)
    app._repo = repo
    app._event_bridge = bridge
    _application_poll(app, clock.now())

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        assert not [
            f for f in fresh_repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY
        ]
        fill_job = daily_open_fill_job_name(symbol, fill_candle.open_time)
        fill_run = fresh_repo.get_scheduler_run(fill_job, fill_candle.open_time)
        gap_run = fresh_repo.get_scheduler_run(
            daily_open_gap_job_name(symbol, fill_candle.open_time),
            fill_candle.open_time,
        )
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        assert fill_run is not None and fill_run.status == SchedulerRunStatus.FAILED
    finally:
        fresh_session.close()
    lock.release()


@pytest.mark.asyncio
async def test_committed_recovery_attempt_survives_deferred_poll(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    from paper_trading.symbol_constraints import StaticSymbolConstraintsProvider

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

    lock_id = 987660200 + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository

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
    assert lock.try_acquire()
    _set_runtime_ready(repo)

    invalid = _valid_constraints(price_tick_size=Decimal("0"))
    valid = _valid_constraints()
    base_bridge = _build_bridge(repo, md, config, clock, lock)
    context_builder = _context_builder({symbol: invalid})
    bridge = MarketEventBridge(
        repository=repo,
        candle_repository=md.repository,
        scheduler=base_bridge.scheduler,
        context_builder=context_builder,
        config=config,
        clock=clock,
        advisory_lock=lock,
        market_data_ready=lambda: md.status(clock.now()).readiness,
    )

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
    _commit_and_ack(bridge, repo, _poll(bridge, clock.now()))

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

    first = _poll(bridge, clock.now())
    _commit_and_ack(bridge, repo, first)
    parent = market_event_job_name(first.outcomes[0].event)
    original_run = repo.get_scheduler_run(parent, fill_candle.open_time)
    assert original_run is not None
    original_run_id = original_run.run_id
    original_error = original_run.error

    context_builder._constraints = StaticSymbolConstraintsProvider({symbol: valid})  # noqa: SLF001
    bridge.recover_permanent_configuration(first.outcomes[0].event)
    repo.session.commit()

    recovery_before = repo.get_active_recovery_attempt(original_run_id)
    assert recovery_before is not None
    recovery_job = recovery_before.job_name
    recovery_run_id = recovery_before.run_id

    original_build = context_builder.build_open_contexts

    def build_with_recovery_defer(sym, candle, eval_time):
        if bridge._active_recovery_context(parent, fill_candle.open_time) is not None:
            raise RetryableContextNotReady("recovery defer test")
        return original_build(sym, candle, eval_time)

    context_builder.build_open_contexts = build_with_recovery_defer  # type: ignore[method-assign]

    deferred = _poll(bridge, clock.now())
    repo.session.commit()
    assert any(o.deferred for o in deferred.outcomes)

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        persisted_original = fresh_repo.get_scheduler_run(parent, fill_candle.open_time)
        assert persisted_original is not None
        assert persisted_original.run_id == original_run_id
        assert persisted_original.status == SchedulerRunStatus.FAILED
        assert persisted_original.error == original_error
        assert persisted_original.resolved_by_run_id is None

        recovery = fresh_repo.get_scheduler_run(recovery_job, fill_candle.open_time)
        assert recovery is not None
        assert recovery.run_id == recovery_run_id
        assert recovery.recovery_of_run_id == original_run_id
        assert recovery.status == SchedulerRunStatus.SKIPPED
        assert recovery.error == RetryableContextNotReady.code
    finally:
        fresh_session.close()
    lock.release()
