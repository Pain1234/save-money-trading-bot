"""Boundary tests for DAILY_CLOSED evaluation due time semantics."""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.clock import FixedClock
from paper_trading.enums import SchedulerRunStatus
from paper_trading.market_events import (
    MarketEvent,
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
    market_event_job_name,
)
from paper_trading.scheduler_context import ProductionContextBuilder
from sqlalchemy import text

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.e2e.helpers import build_breakout_historical_bundle
from tests.paper_trading.integration.lifecycle_helpers import ingest_historical_bundle
from tests.paper_trading.integration.test_production_lifecycle_full import (
    _build_bridge,
    _set_runtime_ready,
)

pytestmark = requires_postgres


def _signal_bundle():
    symbol = "BTC"
    bundle = build_breakout_historical_bundle(symbol, include_exit_candle=True)
    signal = bundle.daily[symbol][-2]
    due = signal.close_time + timedelta(seconds=5)
    return symbol, bundle, signal, due


def _daily_closed_job_name(signal) -> str:
    event = MarketEvent(
        event_type=MarketEventType.DAILY_CLOSED,
        symbol="BTC",
        candle_open_time=signal.open_time,
        provider_received_at=signal.open_time,
    )
    return market_event_job_name(event)


def _clear_market_event_runs(engine, signal) -> None:
    job_name = _daily_closed_job_name(signal)
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM scheduler_runs WHERE job_name = :job_name"),
            {"job_name": job_name},
        )
        conn.commit()


def _enqueue_closed_signal(md, signal) -> None:
    from paper_trading.controlled_market_data import raw_daily

    md.enqueue_raw(
        raw_daily(
            "BTC",
            signal.open_time,
            open_=str(signal.open),
            high=str(signal.high),
            low=str(signal.low),
            close=str(signal.close),
            volume=str(signal.volume),
            is_closed=True,
        )
    )


async def _setup_bridge_at_time(
    migrated_engine,
    postgres_commit_session,
    *,
    clock: FixedClock,
    lock_id_offset: int,
):
    from paper_trading.controlled_market_data import ControlledMarketDataRuntime
    from paper_trading.lock import PostgresAdvisoryLock
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    symbol, bundle, signal, due = _signal_bundle()
    _clear_market_event_runs(migrated_engine, signal)

    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=clock.now() - timedelta(seconds=1),
    )
    await md.start(clock.now())

    lock_id = 987656000 + (os.getpid() % 50000) + lock_id_offset
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        symbols=(symbol,),
        evaluation_delay_seconds=5,
        advisory_lock_id=lock_id,
    )
    repo = PaperTradingRepository(postgres_commit_session)
    lock = PostgresAdvisoryLock(migrated_engine, lock_id)
    assert lock.try_acquire()
    _set_runtime_ready(repo)
    bridge = _build_bridge(repo, md, config, clock, lock)
    return symbol, bundle, signal, due, md, repo, lock, bridge


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_clock_one_microsecond_before_due_no_completed_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """Polls before evaluation_due_at must not consume the event or create FAILED runs."""
    symbol, bundle, signal, due = _signal_bundle()
    before_due = due - timedelta(microseconds=1)
    symbol, bundle, signal, due, md, repo, lock, bridge = await _setup_bridge_at_time(
        migrated_engine,
        postgres_commit_session,
        clock=FixedClock(before_due),
        lock_id_offset=0,
    )

    _enqueue_closed_signal(md, signal)
    await md.process_live(before_due)
    poll = bridge.process_after_poll(before_due)
    repo.session.commit()

    daily_outcomes = [o for o in poll.outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED]
    assert not daily_outcomes
    assert len(repo.list_evaluations(limit=10)) == 0
    assert len(repo.list_intents(limit=10)) == 0
    failed_runs = [
        r
        for r in repo.list_scheduler_runs(limit=20)
        if r.job_name == _daily_closed_job_name(signal)
        and r.status == SchedulerRunStatus.FAILED
    ]
    assert not failed_runs
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_same_bridge_instance_retries_at_due(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """Same detector/bridge instance must emit and complete exactly once when clock reaches due."""
    symbol, bundle, signal, due = _signal_bundle()
    before_due = due - timedelta(microseconds=1)
    symbol, bundle, signal, due, md, repo, lock, bridge = await _setup_bridge_at_time(
        migrated_engine,
        postgres_commit_session,
        clock=FixedClock(before_due),
        lock_id_offset=1,
    )

    _enqueue_closed_signal(md, signal)
    await md.process_live(before_due)
    before_poll = bridge.process_after_poll(before_due)
    repo.session.commit()
    assert not any(
        o.event.event_type == MarketEventType.DAILY_CLOSED for o in before_poll.outcomes
    )

    clock = bridge.clock
    assert isinstance(clock, FixedClock)
    clock.advance_to(due)
    await md.process_live(due)
    at_due_poll = bridge.process_after_poll(due)
    repo.session.commit()

    daily_outcomes = [
        o for o in at_due_poll.outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED
    ]
    assert len(daily_outcomes) == 1
    assert daily_outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert len(repo.list_evaluations(limit=10)) == 1
    assert len(repo.list_intents(limit=10)) >= 1
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_clock_exactly_at_due_one_completed_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol, bundle, signal, due = _signal_bundle()
    symbol, bundle, signal, due, md, repo, lock, bridge = await _setup_bridge_at_time(
        migrated_engine,
        postgres_commit_session,
        clock=FixedClock(due),
        lock_id_offset=2,
    )

    _enqueue_closed_signal(md, signal)
    await md.process_live(due)
    poll = bridge.process_after_poll(due)
    repo.session.commit()

    daily_outcomes = [o for o in poll.outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED]
    assert len(daily_outcomes) == 1
    assert daily_outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert len(repo.list_evaluations(limit=10)) == 1
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_multiple_polls_before_due_no_failed_runs(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol, bundle, signal, due = _signal_bundle()
    before_due = due - timedelta(seconds=2)
    symbol, bundle, signal, due, md, repo, lock, bridge = await _setup_bridge_at_time(
        migrated_engine,
        postgres_commit_session,
        clock=FixedClock(before_due),
        lock_id_offset=3,
    )

    _enqueue_closed_signal(md, signal)
    await md.process_live(before_due)
    for offset in (0, 1, 2):
        poll_time = before_due + timedelta(microseconds=offset)
        bridge.process_after_poll(poll_time)
    repo.session.commit()

    job_name = _daily_closed_job_name(signal)
    daily_runs = [r for r in repo.list_scheduler_runs(limit=50) if r.job_name == job_name]
    assert not daily_runs
    assert len(repo.list_evaluations(limit=10)) == 0
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_replay_after_completed_no_second_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    symbol, bundle, signal, due = _signal_bundle()
    symbol, bundle, signal, due, md, repo, lock, bridge = await _setup_bridge_at_time(
        migrated_engine,
        postgres_commit_session,
        clock=FixedClock(due),
        lock_id_offset=4,
    )

    _enqueue_closed_signal(md, signal)
    await md.process_live(due)
    bridge.process_after_poll(due)
    repo.session.commit()
    eval_count = len(repo.list_evaluations(limit=10))

    poll2 = bridge.process_after_poll(due)
    repo.session.commit()

    daily2 = [o for o in poll2.outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED]
    if daily2:
        assert daily2[0].status == SchedulerRunStatus.COMPLETED
        assert daily2[0].skipped is True
    assert len(repo.list_evaluations(limit=10)) == eval_count
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_restart_between_close_and_due_single_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """Fresh detector after restart must still evaluate exactly once after due."""
    from paper_trading.controlled_market_data import ControlledMarketDataRuntime
    from paper_trading.lock import PostgresAdvisoryLock
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    symbol, bundle, signal, due = _signal_bundle()
    before_due = due - timedelta(seconds=3)
    _clear_market_event_runs(migrated_engine, signal)

    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=before_due - timedelta(seconds=1),
    )
    await md.start(before_due)
    _enqueue_closed_signal(md, signal)
    await md.process_live(before_due)

    lock_id = 987656000 + (os.getpid() % 50000) + 5
    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        symbols=(symbol,),
        evaluation_delay_seconds=5,
        advisory_lock_id=lock_id,
    )
    repo = PaperTradingRepository(postgres_commit_session)
    lock = PostgresAdvisoryLock(migrated_engine, lock_id)
    assert lock.try_acquire()
    _set_runtime_ready(repo)

    pre_restart_clock = FixedClock(before_due)
    pre_bridge = _build_bridge(repo, md, config, pre_restart_clock, lock)
    pre_bridge.process_after_poll(before_due)
    repo.session.commit()
    assert len(repo.list_evaluations(limit=10)) == 0

    post_restart_clock = FixedClock(due)
    post_bridge = _build_bridge(repo, md, config, post_restart_clock, lock)
    await md.process_live(due)
    post_poll = post_bridge.process_after_poll(due)
    repo.session.commit()

    daily_outcomes = [
        o for o in post_poll.outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED
    ]
    assert len(daily_outcomes) == 1
    assert daily_outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert len(repo.list_evaluations(limit=10)) == 1
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_provider_close_within_delay_window_evaluates_after_due(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """Provider close inside the 5s delay window keeps runtime ready; evaluation runs after due."""
    from paper_trading.enums import RuntimeStatus

    symbol, bundle, signal, due = _signal_bundle()
    received_at = signal.close_time + timedelta(seconds=2)
    symbol, bundle, signal, due, md, repo, lock, bridge = await _setup_bridge_at_time(
        migrated_engine,
        postgres_commit_session,
        clock=FixedClock(received_at),
        lock_id_offset=6,
    )

    _enqueue_closed_signal(md, signal)
    await md.process_live(received_at)
    early_poll = bridge.process_after_poll(received_at)
    repo.session.commit()

    assert not any(
        o.event.event_type == MarketEventType.DAILY_CLOSED for o in early_poll.outcomes
    )
    runtime = repo.get_runtime_state()
    assert runtime is not None
    assert runtime.status == RuntimeStatus.READY
    assert len(repo.list_evaluations(limit=10)) == 0

    assert isinstance(bridge.clock, FixedClock)
    bridge.clock.advance_to(due)
    await md.process_live(due)
    due_poll = bridge.process_after_poll(due)
    repo.session.commit()

    daily_outcomes = [o for o in due_poll.outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED]
    assert len(daily_outcomes) == 1
    assert daily_outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert len(repo.list_evaluations(limit=10)) == 1
    lock.release()


def test_handle_daily_closed_unit_before_due_raises() -> None:
    """Offline guard: bridge handler rejects execution before evaluation_due_at."""
    open_time = utc_dt(2024, 1, 30)
    close_time = daily_close(open_time)
    due = close_time + timedelta(seconds=5)
    candle = NormalizedCandle(
        symbol=MarketSymbol("BTC"),
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=close_time,
        open=__import__("decimal").Decimal("100"),
        high=__import__("decimal").Decimal("105"),
        low=__import__("decimal").Decimal("95"),
        close=__import__("decimal").Decimal("100"),
        volume=__import__("decimal").Decimal("1000"),
        is_closed=True,
    )
    repo = MagicMock()
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(candle)
    scheduler = MagicMock()
    context_builder = MagicMock(spec=ProductionContextBuilder)
    advisory_lock = MagicMock()
    advisory_lock.held = True
    clock = FixedClock(due - timedelta(microseconds=1))
    bridge = MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=scheduler,
        context_builder=context_builder,
        config=MagicMock(symbols=("BTC",), evaluation_delay_seconds=5),
        clock=clock,
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5),
    )
    event = MarketEvent(
        event_type=MarketEventType.DAILY_CLOSED,
        symbol="BTC",
        candle_open_time=open_time,
        provider_received_at=clock.now(),
    )
    from paper_trading.market_event_errors import DailyEvaluationNotDue

    with pytest.raises(DailyEvaluationNotDue):
        bridge._handle_daily_closed(event, clock.now())  # noqa: SLF001
    scheduler.run_daily_close_sequence.assert_not_called()
