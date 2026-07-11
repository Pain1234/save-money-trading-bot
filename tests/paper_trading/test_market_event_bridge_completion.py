"""Regression tests for market event bridge completion semantics."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close, expected_close_time
from paper_trading.clock import FixedClock
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import SchedulerRunStatus
from paper_trading.market_events import (
    MarketEvent,
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
    market_event_job_name,
)
from paper_trading.models import SchedulerRun
from paper_trading.scheduler import SchedulerJobName

from tests.paper_trading.conftest_execution import utc_dt


def _daily(
    symbol: str,
    open_time: datetime,
    *,
    low: str = "95",
    close: str = "100",
    is_closed: bool = True,
) -> NormalizedCandle:
    return NormalizedCandle(
        symbol=MarketSymbol(symbol),
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=daily_close(open_time),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


def _completed_run(job_name: str, scheduled_for: datetime) -> SchedulerRun:
    return SchedulerRun(
        run_id=uuid4(),
        job_name=job_name,
        scheduled_for=scheduled_for,
        started_at=scheduled_for,
        completed_at=scheduled_for + timedelta(seconds=1),
        status=SchedulerRunStatus.COMPLETED,
        error=None,
        idempotency_key=f"{job_name}:{scheduled_for.isoformat()}",
    )


def _build_bridge(
    *,
    repo: MagicMock,
    candle_repo: InMemoryCandleRepository,
    clock: FixedClock,
    scheduler: MagicMock | None = None,
) -> MarketEventBridge:
    scheduler = scheduler or MagicMock()
    context_builder = MagicMock()
    context_builder.build_evaluation_context.return_value = {"symbols": {}}
    context_builder.build_stop_context_for_close.return_value = {"daily_candles": {}}
    context_builder.build_open_contexts.return_value = ({}, {})
    context_builder.build_intraday_stop_context.return_value = {"preview_candles": {}}
    scheduler.run_daily_close_sequence.return_value = (
        MagicMock(status=SchedulerRunStatus.COMPLETED),
    )
    scheduler.run_daily_open_sequence.return_value = (
        MagicMock(status=SchedulerRunStatus.COMPLETED),
    )
    scheduler.run_job.return_value = MagicMock(status=SchedulerRunStatus.COMPLETED)
    advisory_lock = MagicMock()
    advisory_lock.held = True
    return MarketEventBridge(
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


def test_daily_closed_returns_persisted_completed_outcome() -> None:
    repo = MagicMock()
    repo.get_scheduler_run.return_value = None
    repo.insert_or_get_scheduler_run.return_value = (
        SchedulerRunRow(
            run_id=uuid4(),
            job_name="me:dc:BTC:20240115T000000Z",
            scheduled_for=utc_dt(2024, 1, 15),
            started_at=utc_dt(2024, 1, 16),
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key="k",
        ),
        True,
    )
    completed = _completed_run("me:dc:BTC:20240115T000000Z", utc_dt(2024, 1, 15))
    repo.get_scheduler_run.side_effect = [None, completed]

    candle_repo = InMemoryCandleRepository()
    open_time = utc_dt(2024, 1, 15)
    candle_repo.upsert(_daily("BTC", open_time, is_closed=True))
    eval_time = utc_dt(2024, 1, 16)
    clock = FixedClock(eval_time)
    bridge = _build_bridge(repo=repo, candle_repo=candle_repo, clock=clock)

    outcomes = bridge.process_after_poll(eval_time)
    assert len(outcomes) == 1
    assert outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert outcomes[0].event.event_type == MarketEventType.DAILY_CLOSED


def test_replay_completed_event_returns_completed_without_rerun() -> None:
    repo = MagicMock()
    scheduled_for = utc_dt(2024, 1, 15)
    job_name = "me:dc:BTC:20240115T000000Z"
    repo.get_scheduler_run.return_value = _completed_run(job_name, scheduled_for)
    scheduler = MagicMock()

    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", scheduled_for, is_closed=True))
    eval_time = utc_dt(2024, 1, 16)
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        scheduler=scheduler,
    )

    outcomes = bridge.process_after_poll(eval_time)
    assert outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert outcomes[0].skipped is True
    scheduler.run_daily_close_sequence.assert_not_called()


def test_missing_context_persists_failed_outcome() -> None:
    repo = MagicMock()
    repo.get_scheduler_run.return_value = None
    repo.insert_or_get_scheduler_run.return_value = (
        SchedulerRunRow(
            run_id=uuid4(),
            job_name="me:dc:BTC:20240115T000000Z",
            scheduled_for=utc_dt(2024, 1, 15),
            started_at=utc_dt(2024, 1, 16),
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key="k",
        ),
        True,
    )
    failed = SchedulerRun(
        run_id=uuid4(),
        job_name="me:dc:BTC:20240115T000000Z",
        scheduled_for=utc_dt(2024, 1, 15),
        started_at=utc_dt(2024, 1, 16),
        completed_at=utc_dt(2024, 1, 16, 0, 0, 1),
        status=SchedulerRunStatus.FAILED,
        error="missing evaluation context for BTC",
        idempotency_key="k2",
    )
    repo.get_scheduler_run.side_effect = [None, failed]

    candle_repo = InMemoryCandleRepository()
    open_time = utc_dt(2024, 1, 15)
    candle_repo.upsert(_daily("BTC", open_time, is_closed=True))
    eval_time = utc_dt(2024, 1, 16)
    context_builder = MagicMock()
    context_builder.build_evaluation_context.return_value = None
    context_builder.build_stop_context_for_close.return_value = {"daily_candles": {}}
    advisory_lock = MagicMock()
    advisory_lock.held = True
    bridge = MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=MagicMock(),
        context_builder=context_builder,
        config=MagicMock(symbols=("BTC",), evaluation_delay_seconds=5),
        clock=FixedClock(eval_time),
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=MarketEventDetector(symbols=("BTC",)),
    )

    outcomes = bridge.process_after_poll(eval_time)
    assert outcomes[0].status == SchedulerRunStatus.FAILED
    assert outcomes[0].error is not None


def test_marker_event_creates_scheduler_run_before_complete() -> None:
    repo = MagicMock()
    repo.get_scheduler_run.return_value = None
    repo.insert_or_get_scheduler_run.return_value = (
        SchedulerRunRow(
            run_id=uuid4(),
            job_name="me:wc:BTC:20240115T000000Z",
            scheduled_for=utc_dt(2024, 1, 15),
            started_at=utc_dt(2024, 1, 16),
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key="k",
        ),
        True,
    )
    completed = _completed_run("me:wc:BTC:20240115T000000Z", utc_dt(2024, 1, 15))
    repo.get_scheduler_run.side_effect = [None, None, completed]

    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(
        NormalizedCandle(
            symbol=MarketSymbol("BTC"),
            timeframe=MarketTimeframe.WEEKLY,
            open_time=utc_dt(2024, 1, 15),
            close_time=expected_close_time(utc_dt(2024, 1, 15), MarketTimeframe.WEEKLY),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("100"),
            volume=Decimal("1000"),
            is_closed=True,
        )
    )
    eval_time = utc_dt(2024, 1, 23)
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
    )

    outcomes = bridge.process_after_poll(eval_time)
    assert outcomes[0].status == SchedulerRunStatus.COMPLETED
    repo.insert_or_get_scheduler_run.assert_called_once()
    repo.complete_scheduler_run.assert_called_once()


def test_backfilled_closed_candle_does_not_emit_daily_open() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",))
    open_time = utc_dt(2024, 1, 16)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    events = detector.detect(repo, utc_dt(2024, 1, 17))
    assert any(e.event_type == MarketEventType.DAILY_CLOSED for e in events)
    assert not any(e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE for e in events)


def test_daily_live_job_name_fits_scheduler_column() -> None:
    event = MarketEvent(
        event_type=MarketEventType.DAILY_LIVE_UPDATE,
        symbol="BTC",
        candle_open_time=utc_dt(2024, 1, 16),
        provider_received_at=utc_dt(2024, 1, 16, 1),
        observed_low=Decimal("86.550000000000000000"),
    )
    job_name = market_event_job_name(event)
    assert len(job_name) <= 64


@pytest.mark.postgres
def test_scheduler_run_job_returns_persisted_status(migrated_engine, db_session) -> None:
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.scheduler import PaperTradingScheduler
    from paper_trading.service_config import PaperServiceConfig

    from tests.paper_trading.conftest import _postgres_url

    config = PaperServiceConfig.from_env(database_url=_postgres_url())
    repo = PaperTradingRepository(db_session)
    scheduler = PaperTradingScheduler(
        repo,
        config,
        evaluation_service=MagicMock(),
        fill_service=MagicMock(),
        stop_service=MagicMock(),
        clock=FixedClock(utc_dt(2024, 1, 16)),
    )
    scheduler.set_jobs_enabled(True)
    scheduled_for = utc_dt(2024, 1, 16)

    first = scheduler.run_job(
        SchedulerJobName.RUNTIME_HEARTBEAT,
        scheduled_for=scheduled_for,
    )
    second = scheduler.run_job(
        SchedulerJobName.RUNTIME_HEARTBEAT,
        scheduled_for=scheduled_for,
    )

    assert first.status == SchedulerRunStatus.COMPLETED
    assert second.status == SchedulerRunStatus.COMPLETED
    assert second.skipped is True
