"""PostgreSQL regression tests for commit/ack boundaries and scheduler outcomes."""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.clock import FixedClock
from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import PaperFillKind, SchedulerRunStatus, TradeIntentStatus
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.market_events import (
    BridgePollResult,
    MarketEvent,
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
    daily_open_gap_job_name,
    market_event_job_name,
)
from paper_trading.scheduler import JobRunOutcome, SchedulerJobName
from paper_trading.scheduler_context import ProductionContextBuilder
from sqlalchemy.orm import sessionmaker

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.conftest_execution import utc_dt
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


@pytest.mark.asyncio
async def test_outer_commit_failure_no_ack_retry_once(
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

    lock_id = 987657000 + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

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
    assert first.events_to_ack
    assert bridge.detector is not None
    assert bridge.detector._trackers[symbol].daily_open_ack_time is None  # noqa: SLF001

    postgres_commit_session.rollback()

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        assert not [
            f
            for f in FreshRepo(fresh).list_fills(limit=10)
            if f.fill_kind == PaperFillKind.ENTRY
        ]

    second = _poll(bridge, clock.now())
    _commit_and_ack(bridge, repo, second)
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    assert bridge.detector._trackers[symbol].daily_open_ack_time == fill_candle.open_time  # noqa: SLF001
    lock.release()


@pytest.mark.asyncio
async def test_ack_after_commit_replay_no_double_fill(
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

    lock_id = 987657100 + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

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
    bridge.acknowledge_committed(first.events_to_ack)

    replay = _poll(bridge, clock.now())
    _commit_and_ack(bridge, repo, replay)

    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    lock.release()


@pytest.mark.asyncio
async def test_advisory_lock_loss_defers_open_subjob(
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

    lock_id = 987657200 + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

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

    real_gap = bridge.scheduler.run_daily_open_gap_stop
    bridge.scheduler.run_daily_open_gap_stop = MagicMock(  # type: ignore[method-assign]
        return_value=(
            JobRunOutcome(
                SchedulerJobName.STOP_TRIGGER_PROCESSING,
                fill_candle.open_time,
                SchedulerRunStatus.SKIPPED,
                skipped=True,
                error="advisory_lock_not_acquired",
            ),
        )
    )
    deferred = _poll(bridge, clock.now())
    repo.session.commit()
    assert deferred.outcomes[0].deferred is True
    assert not deferred.events_to_ack
    gap_job = daily_open_gap_job_name(symbol, fill_candle.open_time)
    gap_run = repo.get_scheduler_run(gap_job, fill_candle.open_time)
    assert gap_run is None or gap_run.status != SchedulerRunStatus.COMPLETED

    bridge.scheduler.run_daily_open_gap_stop = real_gap  # type: ignore[method-assign]
    success = _poll(bridge, clock.now())
    _commit_and_ack(bridge, repo, success)
    assert len([f for f in repo.list_fills(limit=10) if f.fill_kind == PaperFillKind.ENTRY]) == 1
    lock.release()


def test_scheduler_not_ready_is_deferred() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(
        NormalizedCandle(
            symbol=MarketSymbol("BTC"),
            timeframe=MarketTimeframe.DAILY,
            open_time=open_time,
            close_time=daily_close(open_time),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("100"),
            volume=Decimal("1000"),
            is_closed=False,
        )
    )
    repo = MagicMock()
    repo.get_scheduler_run.return_value = None
    repo.insert_or_get_scheduler_run.return_value = (
        SchedulerRunRow(
            run_id=__import__("uuid").uuid4(),
            job_name="me:do:BTC:20240116T000000Z",
            scheduled_for=open_time,
            started_at=eval_time,
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key="k",
        ),
        True,
    )
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (
        JobRunOutcome(
            SchedulerJobName.STOP_TRIGGER_PROCESSING,
            open_time,
            SchedulerRunStatus.SKIPPED,
            skipped=True,
            error="scheduler_not_ready",
        ),
    )
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.return_value = ({}, {})
    advisory_lock = MagicMock()
    advisory_lock.held = True
    bridge = MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=scheduler,
        context_builder=context_builder,
        config=MagicMock(symbols=("BTC",), evaluation_delay_seconds=5, fill_delay_seconds=0),
        clock=FixedClock(eval_time),
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=MarketEventDetector(symbols=("BTC",)),
    )
    result = bridge.process_after_poll(eval_time)
    assert result.outcomes[0].deferred is True
    assert not result.events_to_ack


@pytest.mark.asyncio
async def test_terminal_outcomes_have_persisted_scheduler_runs(
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

    lock_id = 987657300 + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

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
    open_result = _poll(bridge, clock.now())
    _commit_and_ack(bridge, repo, open_result)

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository as FreshRepo

        fresh_repo = FreshRepo(fresh)
        for outcome in open_result.outcomes:
            if outcome.deferred or outcome.retryable:
                continue
            if outcome.status != SchedulerRunStatus.COMPLETED:
                continue
            run = fresh_repo.get_scheduler_run(outcome.job_name, outcome.event.scheduled_for)
            assert run is not None, outcome.job_name
            assert run.status == outcome.status
        parent = market_event_job_name(
            MarketEvent(
                event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
                symbol=symbol,
                candle_open_time=fill_candle.open_time,
                provider_received_at=fill_eval_time,
            )
        )
        parent_run = fresh_repo.get_scheduler_run(parent, fill_candle.open_time)
        assert parent_run is not None
        assert parent_run.status == SchedulerRunStatus.COMPLETED
    lock.release()


@pytest.mark.asyncio
async def test_daily_close_lock_loss_deferred(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol = "BTC"
    bundle = build_breakout_historical_bundle(symbol, include_exit_candle=True)
    signal_candle = bundle.daily[symbol][-2]
    signal_eval_time = eval_time_after_close(signal_candle, delay_seconds=5)

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

    lock_id = 987657400 + (os.getpid() % 50000)
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

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

    real_close = bridge.scheduler.run_daily_close_sequence
    bridge.scheduler.run_daily_close_sequence = MagicMock(  # type: ignore[method-assign]
        return_value=(
            JobRunOutcome(
                SchedulerJobName.DAILY_SIGNAL_EVALUATION,
                signal_candle.close_time,
                SchedulerRunStatus.SKIPPED,
                skipped=True,
                error="advisory_lock_not_acquired",
            ),
        )
    )
    deferred = _poll(bridge, clock.now())
    repo.session.commit()
    daily_outcomes = [
        o for o in deferred.outcomes if o.event.event_type.value == "DAILY_CLOSED"
    ]
    assert daily_outcomes
    assert daily_outcomes[0].deferred is True
    assert not any(
        e.event_type.value == "DAILY_CLOSED" for e in deferred.events_to_ack
    )
    assert len(repo.list_evaluations(limit=10)) == 0

    bridge.scheduler.run_daily_close_sequence = real_close  # type: ignore[method-assign]
    success = _poll(bridge, clock.now())
    _commit_and_ack(bridge, repo, success)
    assert len(repo.list_evaluations(limit=10)) >= 1
    assert len(
        [
            i
            for i in repo.list_intents(limit=10)
            if i.status == TradeIntentStatus.SCHEDULED
        ]
    ) >= 1
    lock.release()
