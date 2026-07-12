"""PostgreSQL regression tests for phased gap/fill daily open (FINAL-001)."""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from backtester.models import HistoricalDataBundle
from market_data.closed import mark_closed_state
from market_data.models import CandleKey, MarketSymbol, MarketTimeframe
from market_data.timeframes import ensure_utc
from paper_trading.application import PaperTradingApplication
from paper_trading.clock import FixedClock
from paper_trading.controlled_market_data import ControlledMarketDataRuntime, raw_daily
from paper_trading.db.orm import TradeIntentRow
from paper_trading.enums import (
    PaperFillKind,
    PaperSide,
    SchedulerRunStatus,
    SignalType,
    TradeIntentStatus,
)
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.market_event_errors import FillNotDue
from paper_trading.market_events import (
    MarketEvent,
    MarketEventType,
    daily_open_gap_job_name,
    daily_open_snapshot_job_name,
    market_event_job_name,
)
from paper_trading.service_config import PaperServiceConfig
from sqlalchemy.orm import sessionmaker

from tests.backtester.conftest import dt
from tests.paper_trading.conftest import _postgres_url, requires_postgres
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
from tests.strategy_engine.conftest import (
    build_flat_daily_series,
    build_rising_monthly_series,
    build_rising_weekly_series,
    make_daily_candle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def _finalize_open_daily_for_strategy(
    md: ControlledMarketDataRuntime,
    *,
    symbol: str,
    open_time,
) -> None:
    """Mark a live open daily candle closed for look-ahead-safe strategy bundles."""
    key = CandleKey(
        symbol=MarketSymbol(symbol),
        timeframe=MarketTimeframe.DAILY,
        open_time=ensure_utc(open_time),
    )
    existing = md.repository._store.get(key)  # noqa: SLF001
    if existing is None:
        return
    md.repository._store[key] = mark_closed_state(  # noqa: SLF001
        existing,
        existing.close_time + timedelta(seconds=1),
    )


def build_gap_below_stop_bundle(symbol: str = "BTC") -> HistoricalDataBundle:
    daily_cs = build_flat_daily_series(symbol, 30, start=dt(2024, 1, 1))
    candles = list(daily_cs.candles)
    last = candles[-1]
    candles[-1] = make_daily_candle(symbol, last.open_time, "100", "130", "99", "125", vol="2000")
    entry_open = last.open_time + timedelta(days=1)
    candles.append(make_daily_candle(symbol, entry_open, "100", "105", "95", "102", vol="1000"))
    hold_open = entry_open + timedelta(days=1)
    candles.append(make_daily_candle(symbol, hold_open, "102", "110", "100", "108", vol="900"))
    gap_open = hold_open + timedelta(days=1)
    candles.append(make_daily_candle(symbol, gap_open, "85", "92", "84", "90", vol="1100"))
    weekly = build_rising_weekly_series(symbol, 55, start_price=Decimal("100"))
    monthly = build_rising_monthly_series(symbol, 25, start_price=Decimal("100"))
    return HistoricalDataBundle(
        daily={symbol: tuple(candles)},
        weekly={symbol: weekly.candles},
        monthly={symbol: monthly.candles},
    )


def _fresh_repo(migrated_engine):
    from paper_trading.repository import PaperTradingRepository

    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    return PaperTradingRepository(session), session


def _seed_scheduled_intent(repo, *, symbol: str, scheduled_fill_time, evaluation_id) -> None:
    from uuid import uuid4

    row = TradeIntentRow(
        intent_id=uuid4(),
        idempotency_key=f"{symbol}:gap-fill-delay:{scheduled_fill_time.isoformat()}",
        symbol=symbol,
        side=PaperSide.LONG.value,
        signal_type=SignalType.BREAKOUT.value,
        signal_time=scheduled_fill_time - timedelta(days=1),
        scheduled_fill_time=scheduled_fill_time,
        requested_entry="100",
        requested_stop="95",
        status=TradeIntentStatus.SCHEDULED.value,
        strategy_evaluation_id=evaluation_id,
        created_at=scheduled_fill_time - timedelta(days=1),
        updated_at=scheduled_fill_time - timedelta(days=1),
    )
    repo.insert_or_get_trade_intent(row)


async def _establish_open_position(
    *,
    migrated_engine,
    postgres_commit_session,
    lock_id: int,
) -> tuple[str, HistoricalDataBundle, ControlledMarketDataRuntime, int]:
    symbol = "BTC"
    bundle = build_gap_below_stop_bundle(symbol)
    signal_candle = bundle.daily[symbol][-4]
    entry_candle = bundle.daily[symbol][-3]
    signal_eval_time = eval_time_after_close(signal_candle, delay_seconds=5)
    entry_eval_time = next_day_open(signal_candle) + timedelta(seconds=1)

    clock = FixedClock(signal_eval_time)
    md = ControlledMarketDataRuntime.create()
    ingest_historical_bundle(
        md,
        bundle,
        symbol,
        daily_count=len(bundle.daily[symbol]) - 3,
        evaluation_time=signal_eval_time - timedelta(seconds=1),
    )
    await md.start(signal_eval_time)

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

    clock.advance_to(entry_eval_time)
    md.enqueue_raw(
        raw_daily(
            symbol,
            entry_candle.open_time,
            open_=str(entry_candle.open),
            high=str(entry_candle.high),
            low=str(entry_candle.low),
            close=str(entry_candle.close),
            volume=str(entry_candle.volume),
            is_closed=False,
        )
    )
    await md.process_live(clock.now())
    _commit_and_ack(bridge, repo, _poll(bridge, clock.now()))
    assert len(repo.get_open_positions()) == 1
    _finalize_open_daily_for_strategy(md, symbol=symbol, open_time=entry_candle.open_time)

    lock.release()
    postgres_commit_session.commit()
    return symbol, bundle, md, lock_id, entry_candle


async def _advance_through_hold_day_close(
    *,
    bundle: HistoricalDataBundle,
    symbol: str,
    md: ControlledMarketDataRuntime,
    migrated_engine,
    postgres_commit_session,
    lock_id: int,
) -> None:
    hold_candle = bundle.daily[symbol][-2]
    hold_eval_time = eval_time_after_close(hold_candle, delay_seconds=5)
    clock = FixedClock(hold_eval_time)
    md.enqueue_raw(
        raw_daily(
            symbol,
            hold_candle.open_time,
            open_=str(hold_candle.open),
            high=str(hold_candle.high),
            low=str(hold_candle.low),
            close=str(hold_candle.close),
            volume=str(hold_candle.volume),
            is_closed=True,
        )
    )
    await md.process_live(clock.now())

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
    _commit_and_ack(bridge, repo, _poll(bridge, clock.now()))
    lock.release()
    postgres_commit_session.commit()


async def _gap_day_application(
    *,
    migrated_engine,
    postgres_commit_session,
    bundle: HistoricalDataBundle,
    symbol: str,
    gap_candle,
    poll_time,
    fill_delay_seconds: int,
    lock_id: int,
    md: ControlledMarketDataRuntime,
    enqueue_gap_candle: bool = True,
):
    clock = FixedClock(poll_time)
    if enqueue_gap_candle:
        md.enqueue_raw(
            raw_daily(
                symbol,
                gap_candle.open_time,
                open_=str(gap_candle.open),
                high=str(gap_candle.high),
                low=str(gap_candle.low),
                close=str(gap_candle.close),
                volume=str(gap_candle.volume),
                is_closed=False,
            )
        )
        await md.process_live(clock.now())

    from paper_trading.repository import PaperTradingRepository

    config = PaperServiceConfig.from_env(
        database_url=_postgres_url(),
        symbols=(symbol,),
        fill_delay_seconds=fill_delay_seconds,
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
    app = PaperTradingApplication(config=config)
    app._repo = repo
    app._event_bridge = bridge
    return app, bridge, repo, lock, clock, config


def _daily_open_outcomes(result) -> list:
    return [
        outcome
        for outcome in result.outcomes
        if outcome.event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE
    ]


def _parent_job(symbol: str, gap_open_time, clock: FixedClock) -> str:
    return market_event_job_name(
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol=symbol,
            candle_open_time=gap_open_time,
            provider_received_at=clock.now(),
        )
    )


@pytest.mark.asyncio
async def test_gap_exit_preserved_when_fill_not_due(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    lock_id = 987670000 + (os.getpid() % 50000)
    fill_delay = 60
    symbol, bundle, md, lock_id, _entry_candle = await _establish_open_position(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )
    await _advance_through_hold_day_close(
        bundle=bundle,
        symbol=symbol,
        md=md,
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )

    gap_candle = bundle.daily[symbol][-1]
    gap_open_time = gap_candle.open_time
    poll_time = gap_open_time + timedelta(seconds=1)

    app, bridge, repo, lock, clock, _config = await _gap_day_application(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        bundle=bundle,
        symbol=symbol,
        gap_candle=gap_candle,
        poll_time=poll_time,
        fill_delay_seconds=fill_delay,
        lock_id=lock_id,
        md=md,
    )

    wallet_before = repo.get_wallet()
    assert wallet_before is not None
    cash_before = wallet_before.cash

    evals = repo.list_evaluations(limit=1)
    assert evals
    _seed_scheduled_intent(
        repo,
        symbol=symbol,
        scheduled_fill_time=gap_open_time,
        evaluation_id=evals[0].evaluation_id,
    )
    repo.session.commit()

    probe = _poll(bridge, clock.now())
    open_outcomes = _daily_open_outcomes(probe)
    assert open_outcomes, f"no daily open outcomes: {[o.event.event_type for o in probe.outcomes]}"
    assert open_outcomes[0].error == FillNotDue.code, open_outcomes[0].error

    _application_poll(app, clock.now())
    assert bridge.detector._trackers[symbol].daily_open_ack_time is None  # noqa: SLF001

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        assert not fresh_repo.get_open_positions()
        assert len([f for f in fresh_repo.list_fills(limit=20) if f.fill_kind == PaperFillKind.EXIT]) == 1
        assert not [
            f
            for f in fresh_repo.list_fills(limit=20)
            if f.fill_kind == PaperFillKind.ENTRY and f.fill_time >= gap_open_time
        ]
        wallet_after = fresh_repo.get_wallet()
        assert wallet_after is not None
        assert wallet_after.cash != cash_before

        gap_run = fresh_repo.get_scheduler_run(
            daily_open_gap_job_name(symbol, gap_open_time), gap_open_time
        )
        parent = fresh_repo.get_scheduler_run(_parent_job(symbol, gap_open_time, clock), gap_open_time)
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        assert parent is None or parent.status != SchedulerRunStatus.COMPLETED
        assert not fresh_repo.get_running_scheduler_runs()
    finally:
        fresh_session.close()
    lock.release()


@pytest.mark.asyncio
async def test_restart_between_gap_and_fill_no_double_exit(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    lock_id = 987670100 + (os.getpid() % 50000)
    fill_delay = 60
    symbol, bundle, md, lock_id, _entry_candle = await _establish_open_position(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )
    await _advance_through_hold_day_close(
        bundle=bundle,
        symbol=symbol,
        md=md,
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )

    gap_candle = bundle.daily[symbol][-1]
    gap_open_time = gap_candle.open_time
    poll_time = gap_open_time + timedelta(seconds=1)

    app, bridge, repo, lock, clock, gap_config = await _gap_day_application(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        bundle=bundle,
        symbol=symbol,
        gap_candle=gap_candle,
        poll_time=poll_time,
        fill_delay_seconds=fill_delay,
        lock_id=lock_id,
        md=md,
    )
    _application_poll(app, clock.now())
    lock.release()
    postgres_commit_session.commit()

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        assert len([f for f in fresh_repo.list_fills(limit=20) if f.fill_kind == PaperFillKind.EXIT]) == 1
        gap_run = fresh_repo.get_scheduler_run(
            daily_open_gap_job_name(symbol, gap_open_time), gap_open_time
        )
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        evals = fresh_repo.list_evaluations(limit=1)
    finally:
        fresh_session.close()

    assert evals
    from paper_trading.repository import PaperTradingRepository

    _seed_scheduled_intent(
        PaperTradingRepository(postgres_commit_session),
        symbol=symbol,
        scheduled_fill_time=gap_open_time,
        evaluation_id=evals[0].evaluation_id,
    )
    postgres_commit_session.commit()

    at_fill_due = gap_open_time + timedelta(seconds=fill_delay + 1)
    app2, bridge2, repo2, lock2, clock2, _ = await _gap_day_application(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        bundle=bundle,
        symbol=symbol,
        gap_candle=gap_candle,
        poll_time=at_fill_due,
        fill_delay_seconds=fill_delay,
        lock_id=lock_id,
        md=md,
        enqueue_gap_candle=False,
    )
    _application_poll(app2, clock2.now())

    fresh_repo2, fresh_session2 = _fresh_repo(migrated_engine)
    try:
        assert len([f for f in fresh_repo2.list_fills(limit=20) if f.fill_kind == PaperFillKind.EXIT]) == 1
        parent = fresh_repo2.get_scheduler_run(
            _parent_job(symbol, gap_open_time, clock2), gap_open_time
        )
        assert parent is not None and parent.status == SchedulerRunStatus.COMPLETED
    finally:
        fresh_session2.close()
    lock2.release()


@pytest.mark.asyncio
async def test_snapshot_failure_after_gap_preserves_exit(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    lock_id = 987670200 + (os.getpid() % 50000)
    symbol, bundle, md, lock_id, _entry_candle = await _establish_open_position(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )
    await _advance_through_hold_day_close(
        bundle=bundle,
        symbol=symbol,
        md=md,
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )

    gap_candle = bundle.daily[symbol][-1]
    gap_open_time = gap_candle.open_time

    app, bridge, repo, lock, clock, _ = await _gap_day_application(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        bundle=bundle,
        symbol=symbol,
        gap_candle=gap_candle,
        poll_time=gap_open_time + timedelta(seconds=1),
        fill_delay_seconds=60,
        lock_id=lock_id,
        md=md,
    )
    _application_poll(app, clock.now())
    lock.release()
    postgres_commit_session.commit()

    evals_repo, evals_session = _fresh_repo(migrated_engine)
    try:
        evals = evals_repo.list_evaluations(limit=1)
    finally:
        evals_session.close()
    assert evals
    from paper_trading.repository import PaperTradingRepository

    _seed_scheduled_intent(
        PaperTradingRepository(postgres_commit_session),
        symbol=symbol,
        scheduled_fill_time=gap_open_time,
        evaluation_id=evals[0].evaluation_id,
    )
    postgres_commit_session.commit()

    app2, bridge2, repo2, lock2, clock2, fill_config = await _gap_day_application(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        bundle=bundle,
        symbol=symbol,
        gap_candle=gap_candle,
        poll_time=gap_open_time + timedelta(seconds=61),
        fill_delay_seconds=0,
        lock_id=lock_id,
        md=md,
    )
    real_snapshot = bridge2.scheduler.run_daily_open_snapshot
    bridge2.scheduler.run_daily_open_snapshot = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("snapshot failed after entry fill")
    )
    _application_poll(app2, clock2.now())

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        assert len([f for f in fresh_repo.list_fills(limit=20) if f.fill_kind == PaperFillKind.EXIT]) == 1
        assert not [
            f
            for f in fresh_repo.list_fills(limit=20)
            if f.fill_kind == PaperFillKind.ENTRY and f.fill_time >= gap_open_time
        ]
        gap_run = fresh_repo.get_scheduler_run(
            daily_open_gap_job_name(symbol, gap_open_time), gap_open_time
        )
        snap_run = fresh_repo.get_scheduler_run(
            daily_open_snapshot_job_name(symbol, gap_open_time), gap_open_time
        )
        parent = fresh_repo.get_scheduler_run(_parent_job(symbol, gap_open_time, clock2), gap_open_time)
        assert gap_run is not None and gap_run.status == SchedulerRunStatus.COMPLETED
        assert snap_run is not None and snap_run.status == SchedulerRunStatus.FAILED
        assert parent is not None and parent.status == SchedulerRunStatus.FAILED
        assert not fresh_repo.get_running_scheduler_runs()
    finally:
        fresh_session.close()

    bridge2.scheduler.run_daily_open_snapshot = real_snapshot  # type: ignore[method-assign]
    app2._config = fill_config
    _application_poll(app2, clock2.now())
    gap_entries = [
        f
        for f in repo2.list_fills(limit=20)
        if f.fill_kind == PaperFillKind.ENTRY and f.fill_time >= gap_open_time
    ]
    assert len(gap_entries) == 1
    lock2.release()


@pytest.mark.asyncio
async def test_fill_delay_zero_gap_before_fill_same_poll(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    lock_id = 987670300 + (os.getpid() % 50000)
    symbol, bundle, md, lock_id, _entry_candle = await _establish_open_position(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )
    await _advance_through_hold_day_close(
        bundle=bundle,
        symbol=symbol,
        md=md,
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        lock_id=lock_id,
    )

    gap_candle = bundle.daily[symbol][-1]
    gap_open_time = gap_candle.open_time
    poll_time = gap_open_time + timedelta(seconds=1)

    fresh_before, session_before = _fresh_repo(migrated_engine)
    exit_before = len([f for f in fresh_before.list_fills(limit=20) if f.fill_kind == PaperFillKind.EXIT])
    session_before.close()

    app, bridge, repo, lock, clock, _ = await _gap_day_application(
        migrated_engine=migrated_engine,
        postgres_commit_session=postgres_commit_session,
        bundle=bundle,
        symbol=symbol,
        gap_candle=gap_candle,
        poll_time=poll_time,
        fill_delay_seconds=0,
        lock_id=lock_id,
        md=md,
    )

    evals = repo.list_evaluations(limit=1)
    assert evals
    _seed_scheduled_intent(
        repo,
        symbol=symbol,
        scheduled_fill_time=gap_open_time,
        evaluation_id=evals[0].evaluation_id,
    )
    repo.session.commit()

    call_order: list[str] = []
    real_gap = bridge.scheduler.run_daily_open_gap_stop
    real_fill = bridge.scheduler.run_daily_open_fill

    def track_gap(**kwargs):
        call_order.append("gap")
        return real_gap(**kwargs)

    def track_fill(**kwargs):
        call_order.append("fill")
        return real_fill(**kwargs)

    bridge.scheduler.run_daily_open_gap_stop = track_gap  # type: ignore[method-assign]
    bridge.scheduler.run_daily_open_fill = track_fill  # type: ignore[method-assign]
    _application_poll(app, clock.now())
    assert call_order.index("gap") < call_order.index("fill")

    fresh_repo, fresh_session = _fresh_repo(migrated_engine)
    try:
        exit_after = len([f for f in fresh_repo.list_fills(limit=20) if f.fill_kind == PaperFillKind.EXIT])
        assert exit_after - exit_before == 1
    finally:
        fresh_session.close()
    lock.release()
