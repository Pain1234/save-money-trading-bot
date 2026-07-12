"""Regression tests for market-data event bridge."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import SchedulerRunStatus
from paper_trading.market_events import (
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
    market_event_job_name,
)
from paper_trading.scheduler import JobRunOutcome
from paper_trading.scheduler_context import ProductionContextBuilder

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


def test_daily_open_event_key_is_deterministic() -> None:
    from paper_trading.market_events import MarketEvent

    event = MarketEvent(
        event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
        symbol="BTC",
        candle_open_time=utc_dt(2024, 1, 16),
        provider_received_at=utc_dt(2024, 1, 16, 1),
    )
    assert market_event_job_name(event) == "me:do:BTC:20240116T000000Z"


def test_detector_daily_open_only_once_after_ack() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",))
    candle = _daily("BTC", utc_dt(2024, 1, 16), is_closed=False)
    repo.upsert(candle)
    eval_time = utc_dt(2024, 1, 16, 1)
    first = detector.detect_candidates(repo, eval_time)
    assert len([e for e in first if e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE]) == 1
    second = detector.detect_candidates(repo, eval_time)
    assert len([e for e in second if e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE]) == 1
    detector.acknowledge_completed(first[0])
    third = detector.detect_candidates(repo, eval_time)
    assert len([e for e in third if e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE]) == 0


def test_live_update_does_not_emit_trailing_event() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",))
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    repo.upsert_live(_daily("BTC", open_time, low="95", is_closed=False), eval_time)
    open_events = detector.detect_candidates(repo, eval_time)
    assert len(open_events) == 1
    detector.acknowledge_completed(open_events[0])
    repo.upsert_live(_daily("BTC", open_time, low="90", is_closed=False), eval_time)
    events = detector.detect_candidates(repo, utc_dt(2024, 1, 16, 2))
    assert any(e.event_type == MarketEventType.DAILY_LIVE_UPDATE for e in events)
    assert not any(e.event_type == MarketEventType.DAILY_CLOSED for e in events)


def test_closed_candle_emits_daily_closed_once() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5)
    open_time = utc_dt(2024, 1, 15)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    due = daily_close(open_time) + timedelta(seconds=5)
    first = detector.detect_candidates(repo, due)
    assert len([e for e in first if e.event_type == MarketEventType.DAILY_CLOSED]) == 1
    for event in first:
        if event.event_type == MarketEventType.DAILY_CLOSED:
            detector.acknowledge_completed(event)
    second = detector.detect_candidates(repo, due + timedelta(hours=1))
    assert len([e for e in first if e.event_type == MarketEventType.DAILY_CLOSED]) == 1
    assert len([e for e in second if e.event_type == MarketEventType.DAILY_CLOSED]) == 0


def test_daily_closed_not_emitted_before_evaluation_due() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5)
    open_time = utc_dt(2024, 1, 15)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    due = daily_close(open_time) + timedelta(seconds=5)
    before_due = due - timedelta(microseconds=1)
    events = detector.detect(repo, before_due)
    assert not any(e.event_type == MarketEventType.DAILY_CLOSED for e in events)
    assert detector._trackers["BTC"].daily_closed_ack_time is None  # noqa: SLF001


def test_daily_closed_emitted_at_due_on_same_detector_instance() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5)
    open_time = utc_dt(2024, 1, 15)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    due = daily_close(open_time) + timedelta(seconds=5)
    before = detector.detect(repo, due - timedelta(microseconds=1))
    assert not any(e.event_type == MarketEventType.DAILY_CLOSED for e in before)
    at_due = detector.detect(repo, due)
    assert len([e for e in at_due if e.event_type == MarketEventType.DAILY_CLOSED]) == 1


def test_queue_overflow_processes_partial_batch() -> None:
    from paper_trading.market_events import MarketEvent

    scheduled_for = utc_dt(2024, 1, 16)
    runs: dict[tuple[str, datetime], SchedulerRunRow] = {}

    def get_scheduler_run(job_name: str, sched: datetime) -> SchedulerRunRow | None:
        return runs.get((job_name, sched))

    def insert_or_get_scheduler_run(row: SchedulerRunRow) -> tuple[SchedulerRunRow, bool]:
        key = (row.job_name, row.scheduled_for)
        if key in runs:
            return runs[key], False
        runs[key] = row
        return row, True

    def complete_scheduler_run(
        *,
        job_name: str,
        scheduled_for: datetime,
        status: SchedulerRunStatus,
        completed_at: datetime,
        error: str | None,
    ) -> None:
        key = (job_name, scheduled_for)
        existing = runs[key]
        runs[key] = SchedulerRunRow(
            run_id=existing.run_id,
            job_name=existing.job_name,
            scheduled_for=existing.scheduled_for,
            started_at=existing.started_at,
            status=status.value,
            idempotency_key=existing.idempotency_key,
            completed_at=completed_at,
            error=error,
        )

    repo = MagicMock()
    repo.get_scheduler_run.side_effect = get_scheduler_run
    repo.insert_or_get_scheduler_run.side_effect = insert_or_get_scheduler_run
    repo.complete_scheduler_run.side_effect = complete_scheduler_run
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(
        _daily("BTC", utc_dt(2024, 1, 16), is_closed=False, low="95")
    )
    def _completed_job(job_name: str) -> tuple[JobRunOutcome, ...]:
        return (
            JobRunOutcome(
                job_name=job_name,
                scheduled_for=scheduled_for,
                status=SchedulerRunStatus.COMPLETED,
                skipped=False,
            ),
        )

    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.side_effect = lambda **_: _completed_job("gap")
    scheduler.run_daily_open_fill.side_effect = lambda **_: _completed_job("fill")
    scheduler.run_daily_open_snapshot.side_effect = lambda **_: _completed_job("snap")
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.return_value = ({}, {})
    advisory_lock = MagicMock()
    advisory_lock.held = True

    detector = MagicMock()
    detector.detect_candidates.return_value = (
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol="BTC",
            candle_open_time=utc_dt(2024, 1, 16),
            provider_received_at=utc_dt(2024, 1, 16, 1),
            observed_low=Decimal("95"),
        ),
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol="ETH",
            candle_open_time=utc_dt(2024, 1, 16),
            provider_received_at=utc_dt(2024, 1, 16, 1),
            observed_low=Decimal("95"),
        ),
    )
    detector.acknowledge_completed = MagicMock()

    bridge = MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=scheduler,
        context_builder=context_builder,
        config=MagicMock(symbols=("BTC", "ETH"), evaluation_delay_seconds=5, fill_delay_seconds=0),
        clock=MagicMock(now=lambda: utc_dt(2024, 1, 16)),
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=detector,
        max_events_per_poll=1,
    )
    result = bridge.process_after_poll(utc_dt(2024, 1, 16, 1))
    assert bridge.queue_overflow is True
    assert len(result.outcomes) == 1
    assert len(result.events_to_ack) == 1
    bridge.acknowledge_committed(result.events_to_ack)
    detector.acknowledge_completed.assert_called_once()
