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


def _clear_market_event_runs(engine, signal) -> None:
    event = MarketEvent(
        event_type=MarketEventType.DAILY_CLOSED,
        symbol="BTC",
        candle_open_time=signal.open_time,
        provider_received_at=signal.open_time,
    )
    job_name = market_event_job_name(event)
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM scheduler_runs WHERE job_name = :job_name"),
            {"job_name": job_name},
        )
        conn.commit()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_clock_one_microsecond_before_due_no_completed_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """evaluation_due_at = close_time + delay; earlier clock must not complete evaluation."""
    from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
    from paper_trading.lock import PostgresAdvisoryLock
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    symbol, bundle, signal, due = _signal_bundle()
    before_due = due - timedelta(microseconds=1)
    _clear_market_event_runs(migrated_engine, signal)
    clock = FixedClock(before_due)

    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=before_due - timedelta(seconds=1),
    )
    await md.start(before_due)

    lock_id = 987656000 + (os.getpid() % 50000)
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

    md.enqueue_raw(
        raw_daily(
            symbol,
            signal.open_time,
            open_=str(signal.open),
            high=str(signal.high),
            low=str(signal.low),
            close=str(signal.close),
            volume=str(signal.volume),
            is_closed=True,
        )
    )
    await md.process_live(clock.now())
    outcomes = bridge.process_after_poll(clock.now())
    repo.session.commit()

    daily_outcomes = [o for o in outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED]
    assert daily_outcomes
    assert all(o.status == SchedulerRunStatus.FAILED for o in daily_outcomes)
    assert len(repo.list_evaluations(limit=10)) == 0
    assert len(repo.list_intents(limit=10)) == 0
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_clock_exactly_at_due_one_completed_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
    from paper_trading.lock import PostgresAdvisoryLock
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    symbol, bundle, signal, due = _signal_bundle()
    _clear_market_event_runs(migrated_engine, signal)
    clock = FixedClock(due)

    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=due - timedelta(seconds=1),
    )
    await md.start(due)

    lock_id = 987656000 + (os.getpid() % 50000) + 1
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

    md.enqueue_raw(
        raw_daily(
            symbol,
            signal.open_time,
            open_=str(signal.open),
            high=str(signal.high),
            low=str(signal.low),
            close=str(signal.close),
            volume=str(signal.volume),
            is_closed=True,
        )
    )
    await md.process_live(clock.now())
    outcomes = bridge.process_after_poll(clock.now())
    repo.session.commit()

    daily_outcomes = [o for o in outcomes if o.event.event_type == MarketEventType.DAILY_CLOSED]
    assert len(daily_outcomes) == 1
    assert daily_outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert len(repo.list_evaluations(limit=10)) == 1
    lock.release()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_replay_after_completed_no_second_evaluation(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
    from paper_trading.lock import PostgresAdvisoryLock
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    symbol, bundle, signal, due = _signal_bundle()
    _clear_market_event_runs(migrated_engine, signal)
    clock = FixedClock(due)

    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 2,
        evaluation_time=due - timedelta(seconds=1),
    )
    await md.start(due)

    lock_id = 987656000 + (os.getpid() % 50000) + 2
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

    md.enqueue_raw(
        raw_daily(
            symbol,
            signal.open_time,
            open_=str(signal.open),
            high=str(signal.high),
            low=str(signal.low),
            close=str(signal.close),
            volume=str(signal.volume),
            is_closed=True,
        )
    )
    await md.process_live(clock.now())
    bridge.process_after_poll(clock.now())
    repo.session.commit()
    eval_count = len(repo.list_evaluations(limit=10))

    outcomes2 = bridge.process_after_poll(clock.now())
    repo.session.commit()

    daily2 = [o for o in outcomes2 if o.event.event_type == MarketEventType.DAILY_CLOSED]
    if daily2:
        assert daily2[0].status == SchedulerRunStatus.COMPLETED
        assert daily2[0].skipped is True
    assert len(repo.list_evaluations(limit=10)) == eval_count
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
        detector=MarketEventDetector(symbols=("BTC",)),
    )
    event = bridge.detector.detect(candle_repo, clock.now())[0]
    with pytest.raises(RuntimeError, match="daily evaluation not due"):
        bridge._handle_daily_closed(event, clock.now())  # noqa: SLF001
    scheduler.run_daily_close_sequence.assert_not_called()
