"""PostgreSQL regression tests for transaction boundaries and recovery audit integrity."""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
import sqlalchemy.exc
from paper_trading.application import PaperTradingApplication
from paper_trading.clock import FixedClock
from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
from paper_trading.enums import PaperFillKind, SchedulerRunStatus
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.market_event_errors import PERMANENT_CONFIGURATION_INVALID_TICK_SIZE
from paper_trading.market_events import (
    BridgePollResult,
    MarketEventBridge,
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
from tests.paper_trading.test_permanent_configuration_failures import (
    _context_builder,
    _patch_strategy_engine_success,
    _valid_constraints,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def _poll(bridge: MarketEventBridge, evaluation_time) -> BridgePollResult:
    return bridge.process_after_poll(evaluation_time)


def _commit_and_ack(
    bridge: MarketEventBridge,
    repo,
    result: BridgePollResult,
) -> None:
    repo.session.commit()
    bridge.acknowledge_committed(result.events_to_ack)
    bridge.acknowledge_terminal_failed_committed(result.events_terminal_failed)


def _application_poll(app: PaperTradingApplication, evaluation_time) -> None:
    app._process_committed_market_event_poll(evaluation_time)


@pytest.mark.asyncio
async def test_application_commit_failure_rolls_back_and_retries_once(
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

    lock_id = 987658000 + (os.getpid() % 50000)
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

    app = PaperTradingApplication(config=config)
    app._repo = repo
    app._event_bridge = bridge

    first_poll = _poll(bridge, clock.now())
    assert first_poll.events_to_ack
    assert bridge.detector is not None
    assert bridge.detector._trackers[symbol].daily_open_ack_time is None  # noqa: SLF001

    real_commit = postgres_commit_session.commit
    commit_calls = {"count": 0}

    def failing_commit() -> None:
        commit_calls["count"] += 1
        if commit_calls["count"] == 1:
            raise sqlalchemy.exc.OperationalError(
                "commit",
                {},
                RuntimeError("simulated outer commit failure"),
            )
        return real_commit()

    postgres_commit_session.commit = failing_commit  # type: ignore[method-assign]

    with pytest.raises(sqlalchemy.exc.OperationalError):
        _application_poll(app, clock.now())

    assert bridge.detector._trackers[symbol].daily_open_ack_time is None  # noqa: SLF001

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        assert not [
            f
            for f in FreshRepo(fresh).list_fills(limit=10)
            if f.fill_kind == PaperFillKind.ENTRY
        ]
        assert not FreshRepo(fresh).get_running_scheduler_runs()

    _application_poll(app, clock.now())
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    assert bridge.detector._trackers[symbol].daily_open_ack_time == fill_candle.open_time  # noqa: SLF001
    lock.release()


@pytest.mark.asyncio
async def test_ack_failure_after_commit_rebuilds_without_double_fill(
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

    lock_id = 987658100 + (os.getpid() % 50000)
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

    first = _poll(bridge, clock.now())
    repo.session.commit()

    ack_calls = {"count": 0}
    real_ack = bridge.acknowledge_committed

    def failing_ack(events) -> None:
        ack_calls["count"] += 1
        if ack_calls["count"] == 1:
            raise RuntimeError("simulated ack failure after commit")
        return real_ack(events)

    bridge.acknowledge_committed = failing_ack  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated ack failure"):
        bridge.acknowledge_committed(first.events_to_ack)

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        fresh_repo = FreshRepo(fresh)
        assert len([f for f in fresh_repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
        parent = market_event_job_name(first.outcomes[0].event)
        parent_run = fresh_repo.get_scheduler_run(parent, fill_candle.open_time)
        assert parent_run is not None
        assert parent_run.status == SchedulerRunStatus.COMPLETED

    bridge2 = _build_bridge(repo, md, config, clock, lock)
    replay = _poll(bridge2, clock.now())
    _commit_and_ack(bridge2, repo, replay)
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    lock.release()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failing_stage",
    ["gap", "fill", "snapshot"],
)
async def test_daily_open_subjob_failure_marks_parent_failed_and_rolls_back_on_commit_error(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
    failing_stage: str,
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

    lock_id = 987658200 + (os.getpid() % 50000)
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

    boom = RuntimeError(f"{failing_stage}_handler_failed")
    if failing_stage == "gap":
        bridge.scheduler.run_daily_open_gap_stop = MagicMock(side_effect=boom)  # type: ignore[method-assign]
    elif failing_stage == "fill":
        bridge.scheduler.run_daily_open_fill = MagicMock(side_effect=boom)  # type: ignore[method-assign]
    else:
        bridge.scheduler.run_daily_open_snapshot = MagicMock(side_effect=boom)  # type: ignore[method-assign]

    result = _poll(bridge, clock.now())
    assert result.outcomes
    assert result.outcomes[0].status == SchedulerRunStatus.FAILED
    assert not result.events_to_ack

    parent = market_event_job_name(result.outcomes[0].event)
    parent_run = repo.get_scheduler_run(parent, fill_candle.open_time)
    assert parent_run is not None
    assert parent_run.status == SchedulerRunStatus.FAILED

    gap_job = daily_open_gap_job_name(symbol, fill_candle.open_time)
    fill_job = daily_open_fill_job_name(symbol, fill_candle.open_time)
    snap_job = daily_open_snapshot_job_name(symbol, fill_candle.open_time)
    gap_run = repo.get_scheduler_run(gap_job, fill_candle.open_time)
    fill_run = repo.get_scheduler_run(fill_job, fill_candle.open_time)
    snap_run = repo.get_scheduler_run(snap_job, fill_candle.open_time)

    if failing_stage == "gap":
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.FAILED
        assert fill_run is None
        assert snap_run is None
    elif failing_stage == "fill":
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        assert fill_run is not None and fill_run.status == SchedulerRunStatus.FAILED
        assert snap_run is None
    else:
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        assert fill_run is not None and fill_run.status == SchedulerRunStatus.COMPLETED
        assert snap_run is not None and snap_run.status == SchedulerRunStatus.FAILED

    postgres_commit_session.rollback()
    assert not repo.get_running_scheduler_runs()

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        assert not [
            f
            for f in FreshRepo(fresh).list_fills(limit=10)
            if f.fill_kind == PaperFillKind.ENTRY
        ]
    lock.release()


@pytest.mark.asyncio
async def test_application_rollback_on_process_after_poll_exception(
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

    lock_id = 987658300 + (os.getpid() % 50000)
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

    app = PaperTradingApplication(config=config)
    app._repo = repo
    app._event_bridge = bridge
    bridge.process_after_poll = MagicMock(side_effect=RuntimeError("poll processing failed"))  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="poll processing failed"):
        _application_poll(app, clock.now())

    assert not repo.get_running_scheduler_runs()
    lock.release()


@pytest.mark.asyncio
async def test_immutable_original_failed_after_deferred_recovery_attempt(
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

    lock_id = 987658400 + (os.getpid() % 50000)
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

    invalid = _valid_constraints(price_tick_size=__import__("decimal").Decimal("0"))
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
    original_error = first.outcomes[0].error
    parent = market_event_job_name(first.outcomes[0].event)
    original_run = repo.get_scheduler_run(parent, fill_candle.open_time)
    assert original_run is not None
    assert original_run.status == SchedulerRunStatus.FAILED
    original_run_id = original_run.run_id

    context_builder._constraints = StaticSymbolConstraintsProvider({symbol: valid})  # noqa: SLF001
    bridge.recover_permanent_configuration(first.outcomes[0].event)
    repo.session.commit()

    from paper_trading.market_event_errors import RetryableContextNotReady

    original_build = context_builder.build_open_contexts

    def build_with_recovery_defer(symbol, candle, eval_time):
        if bridge._active_recovery_context(parent, fill_candle.open_time) is not None:
            raise RetryableContextNotReady("recovery defer test")
        return original_build(symbol, candle, eval_time)

    context_builder.build_open_contexts = build_with_recovery_defer  # type: ignore[method-assign]

    deferred = _poll(bridge, clock.now())
    repo.session.commit()
    open_outcomes = [
        outcome
        for outcome in deferred.outcomes
        if outcome.event.event_type.value == "DAILY_OPEN_AVAILABLE"
    ]
    assert open_outcomes
    assert open_outcomes[0].deferred is True

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        fresh_repo = FreshRepo(fresh)
        persisted_original = fresh_repo.get_scheduler_run(parent, fill_candle.open_time)
        assert persisted_original is not None
        assert persisted_original.run_id == original_run_id
        assert persisted_original.status == SchedulerRunStatus.FAILED
        assert persisted_original.error == original_error
        assert persisted_original.resolved_by_run_id is None
        recovery = fresh_repo.get_active_recovery_attempt(original_run_id)
        assert recovery is None
    lock.release()


@pytest.mark.asyncio
async def test_successful_recovery_attempt_preserves_original_failed_audit(
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

    lock_id = 987658500 + (os.getpid() % 50000)
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

    invalid = _valid_constraints(price_tick_size=__import__("decimal").Decimal("0"))
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
    original_error = original_run.error
    assert original_error == PERMANENT_CONFIGURATION_INVALID_TICK_SIZE

    context_builder._constraints = StaticSymbolConstraintsProvider({symbol: valid})  # noqa: SLF001
    bridge.recover_permanent_configuration(first.outcomes[0].event)
    repo.session.commit()

    with _patch_strategy_engine_success():
        second = _poll(bridge, clock.now())
        _commit_and_ack(bridge, repo, second)

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        fresh_repo = FreshRepo(fresh)
        persisted_original = fresh_repo.get_scheduler_run(parent, fill_candle.open_time)
        assert persisted_original is not None
        assert persisted_original.status == SchedulerRunStatus.FAILED
        assert persisted_original.error == original_error
        assert persisted_original.resolved_by_run_id is not None
        recovery_runs = [
            run
            for run in fresh_repo.list_scheduler_runs(limit=20)
            if ":recovery:" in run.job_name
        ]
        assert any(run.status == SchedulerRunStatus.COMPLETED for run in recovery_runs)
    lock.release()
