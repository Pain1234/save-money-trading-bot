"""Regression tests for daily open event lifecycle (O-001, O-003, O-004)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.clock import FixedClock
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import SchedulerRunStatus
from paper_trading.market_event_errors import (
    FillNotDue,
    PermanentConfigurationFailure,
    RetryableContextNotReady,
)
from paper_trading.market_events import (
    MarketEvent,
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
    daily_open_fill_job_name,
    daily_open_gap_job_name,
    daily_open_snapshot_job_name,
    market_event_job_name,
)
from paper_trading.models import SchedulerRun
from paper_trading.scheduler_context import ProductionContextBuilder

from tests.paper_trading.bridge_test_helpers import ack_result
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


def _open_subjob_outcome() -> MagicMock:
    return MagicMock(status=SchedulerRunStatus.COMPLETED, skipped=False, error=None)


def _build_bridge(
    *,
    repo: MagicMock,
    candle_repo: InMemoryCandleRepository,
    clock: FixedClock,
    context_builder: MagicMock,
    scheduler: MagicMock | None = None,
    fill_delay_seconds: int = 0,
    detector: MarketEventDetector | None = None,
    max_events_per_poll: int = 256,
) -> MarketEventBridge:
    scheduler = scheduler or MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(),)
    scheduler.run_job.return_value = _open_subjob_outcome()
    advisory_lock = MagicMock()
    advisory_lock.held = True
    return MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=scheduler,
        context_builder=context_builder,
        config=MagicMock(
            symbols=("BTC",),
            evaluation_delay_seconds=5,
            fill_delay_seconds=fill_delay_seconds,
        ),
        clock=clock,
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=detector or MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5),
        max_events_per_poll=max_events_per_poll,
    )


def _repo_with_subjob_tracking() -> MagicMock:
    repo = MagicMock()
    runs: dict[tuple[str, datetime], SchedulerRunRow] = {}
    errors: dict[tuple[str, datetime], str | None] = {}

    def get_run(job_name: str, scheduled_for: datetime) -> SchedulerRun | None:
        row = runs.get((job_name, scheduled_for))
        if row is None:
            return None
        key = (job_name, scheduled_for)
        return SchedulerRun(
            run_id=row.run_id,
            job_name=row.job_name,
            scheduled_for=row.scheduled_for,
            started_at=row.started_at,
            completed_at=row.started_at,
            status=SchedulerRunStatus(row.status),
            error=errors.get(key),
            idempotency_key=row.idempotency_key,
        )

    def insert_or_get(job_row: SchedulerRunRow) -> tuple[SchedulerRunRow, bool]:
        key = (job_row.job_name, job_row.scheduled_for)
        if key in runs:
            return runs[key], False
        runs[key] = job_row
        return job_row, True

    def complete_run(
        *,
        job_name: str,
        scheduled_for: datetime,
        status: SchedulerRunStatus,
        completed_at: datetime,
        error: str | None,
    ) -> None:
        key = (job_name, scheduled_for)
        row = runs.get(key)
        if row is not None:
            row.status = status.value
            errors[key] = error

    repo.get_scheduler_run.side_effect = get_run
    repo.insert_or_get_scheduler_run.side_effect = insert_or_get
    repo.complete_scheduler_run.side_effect = complete_run
    return repo


def test_same_bridge_retry_transient_open_context() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    detector = MarketEventDetector(symbols=("BTC",))
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = [
        RetryableContextNotReady("atr14 not available"),
        ({}, {}),
    ]
    repo = _repo_with_subjob_tracking()
    clock = FixedClock(eval_time)
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(),)
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=clock,
        context_builder=context_builder,
        scheduler=scheduler,
        detector=detector,
    )

    first = bridge.process_after_poll(eval_time)
    assert len(first.outcomes) == 1
    assert first.outcomes[0].deferred is True
    assert first.outcomes[0].retryable is True
    assert first.outcomes[0].error == RetryableContextNotReady.code
    assert first.outcomes[0].status != SchedulerRunStatus.FAILED
    assert detector._trackers["BTC"].daily_open_ack_time is None  # noqa: SLF001
    assert bridge.deferred_events is True
    scheduler.run_daily_open_gap_stop.assert_not_called()

    second = bridge.process_after_poll(eval_time)
    ack_result(bridge, second)
    assert len(second.outcomes) == 1
    assert second.outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert second.outcomes[0].skipped is False
    assert detector._trackers["BTC"].daily_open_ack_time == open_time  # noqa: SLF001
    assert bridge.deferred_events is False
    scheduler.run_daily_open_gap_stop.assert_called_once()


def test_restart_retry_after_transient_open_context() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = [
        RetryableContextNotReady("bundle not usable"),
        ({}, {}),
    ]

    repo1 = _repo_with_subjob_tracking()
    detector1 = MarketEventDetector(symbols=("BTC",))
    bridge1 = _build_bridge(
        repo=repo1,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        detector=detector1,
    )
    bridge1.process_after_poll(eval_time)
    assert detector1._trackers["BTC"].daily_open_ack_time is None  # noqa: SLF001

    repo2 = _repo_with_subjob_tracking()
    detector2 = MarketEventDetector(symbols=("BTC",))
    bridge2 = _build_bridge(
        repo=repo2,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        detector=detector2,
    )
    outcomes = bridge2.process_after_poll(eval_time)
    ack_result(bridge2, outcomes)
    assert outcomes.outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert detector2._trackers["BTC"].daily_open_ack_time == open_time  # noqa: SLF001


def test_permanent_missing_constraints_fails_closed() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = PermanentConfigurationFailure(
        "missing symbol constraints for BTC",
        error_code=PermanentConfigurationFailure.code,
    )
    repo = _repo_with_subjob_tracking()
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
    )
    outcomes = bridge.process_after_poll(eval_time)
    ack_result(bridge, outcomes)
    assert outcomes.outcomes[0].status == SchedulerRunStatus.FAILED
    assert outcomes.outcomes[0].error == PermanentConfigurationFailure.code
    assert outcomes.outcomes[0].terminal_failed is True
    assert len(outcomes.events_terminal_failed) == 1
    assert bridge.detector._trackers["BTC"].daily_open_ack_time is None  # noqa: SLF001
    assert bridge.detector._trackers["BTC"].daily_open_terminal_failed_time == open_time  # noqa: SLF001

    retry = bridge.process_after_poll(eval_time)
    assert len(retry.outcomes) == 0
    assert context_builder.build_open_contexts.call_count == 1


def test_context_never_ready_stays_deferred_without_failed_flood() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = RetryableContextNotReady("not ready")
    repo = _repo_with_subjob_tracking()
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
    )
    for _ in range(5):
        outcomes = bridge.process_after_poll(eval_time)
        assert outcomes.outcomes[0].deferred is True
        assert outcomes.outcomes[0].status != SchedulerRunStatus.FAILED
    assert bridge.deferred_events is True
    assert repo.complete_scheduler_run.call_count == 0


def test_overflow_partial_batch_preserves_remaining_events() -> None:
    candle_repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC", "ETH", "SOL"))
    eval_time = utc_dt(2024, 1, 16, 1)
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, utc_dt(2024, 1, 16), is_closed=False))

    repo = _repo_with_subjob_tracking()
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.return_value = ({}, {})
    eval_time = utc_dt(2024, 1, 16, 1)
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        max_events_per_poll=2,
    )
    bridge.detector = detector

    first = bridge.process_after_poll(eval_time)
    ack_result(bridge, first)
    assert bridge.queue_overflow is True
    assert len(first.outcomes) == 2
    assert detector._trackers["BTC"].daily_open_ack_time is not None  # noqa: SLF001
    assert detector._trackers["ETH"].daily_open_ack_time is not None  # noqa: SLF001
    assert detector._trackers["SOL"].daily_open_ack_time is None  # noqa: SLF001

    second = bridge.process_after_poll(eval_time)
    ack_result(bridge, second)
    assert len(second.outcomes) == 1
    assert second.outcomes[0].event.symbol == "SOL"
    assert detector._trackers["SOL"].daily_open_ack_time is not None  # noqa: SLF001


def test_fill_delay_gap_immediate_fill_deferred_until_due() -> None:
    open_time = utc_dt(2024, 1, 16)
    fill_delay = 60
    before_due = open_time + timedelta(seconds=fill_delay - 1)
    at_due = open_time + timedelta(seconds=fill_delay)

    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.return_value = ({}, {})
    repo = _repo_with_subjob_tracking()
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(),)

    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(before_due),
        context_builder=context_builder,
        scheduler=scheduler,
        fill_delay_seconds=fill_delay,
    )
    first = bridge.process_after_poll(before_due)
    assert first.outcomes[0].deferred is True
    assert first.outcomes[0].error == FillNotDue.code
    assert bridge.detector._trackers["BTC"].daily_open_ack_time is None  # noqa: SLF001
    scheduler.run_daily_open_gap_stop.assert_called_once()
    scheduler.run_daily_open_fill.assert_not_called()

    bridge.clock = FixedClock(at_due)
    second = bridge.process_after_poll(at_due)
    ack_result(bridge, second)
    assert second.outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert bridge.detector._trackers["BTC"].daily_open_ack_time == open_time  # noqa: SLF001
    assert scheduler.run_daily_open_gap_stop.call_count == 1
    scheduler.run_daily_open_fill.assert_called_once()
    scheduler.run_daily_open_snapshot.assert_called_once()


def test_fill_delay_zero_runs_all_subjobs_immediately() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = open_time + timedelta(seconds=1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.return_value = ({}, {})
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(),)
    repo = _repo_with_subjob_tracking()
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        fill_delay_seconds=0,
    )
    outcomes = bridge.process_after_poll(eval_time)
    ack_result(bridge, outcomes)
    assert outcomes.outcomes[0].status == SchedulerRunStatus.COMPLETED
    scheduler.run_daily_open_gap_stop.assert_called_once()
    scheduler.run_daily_open_fill.assert_called_once()
    scheduler.run_daily_open_snapshot.assert_called_once()


def test_completed_event_does_not_retry() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    repo = _repo_with_subjob_tracking()
    scheduled_for = open_time
    for job in (
        daily_open_gap_job_name("BTC", scheduled_for),
        daily_open_fill_job_name("BTC", scheduled_for),
        daily_open_snapshot_job_name("BTC", scheduled_for),
    ):
        repo.insert_or_get_scheduler_run(
            SchedulerRunRow(
                run_id=uuid4(),
                job_name=job,
                scheduled_for=scheduled_for,
                started_at=eval_time,
                status=SchedulerRunStatus.COMPLETED.value,
                idempotency_key=job,
            )
        )
    context_builder = MagicMock(spec=ProductionContextBuilder)
    scheduler = MagicMock()
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
    )
    outcomes = bridge.process_after_poll(eval_time)
    assert outcomes.outcomes[0].skipped is True
    context_builder.build_open_contexts.assert_not_called()
    scheduler.run_daily_open_gap_stop.assert_not_called()


def test_detector_re_emits_until_acknowledged() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",))
    open_time = utc_dt(2024, 1, 16)
    repo.upsert(_daily("BTC", open_time, is_closed=False))
    eval_time = utc_dt(2024, 1, 16, 1)
    first = detector.detect_candidates(repo, eval_time)
    second = detector.detect_candidates(repo, eval_time)
    assert len(first) == 1
    assert len(second) == 1
    event = first[0]
    detector.acknowledge_completed(event)
    third = detector.detect_candidates(repo, eval_time)
    assert not any(e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE for e in third)


def test_daily_closed_deferred_on_missing_evaluation_context() -> None:
    open_time = utc_dt(2024, 1, 15)
    eval_time = daily_close(open_time) + timedelta(seconds=5)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=True))
    repo = _repo_with_subjob_tracking()
    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_evaluation_context.side_effect = RetryableContextNotReady("not ready")
    context_builder.build_stop_context_for_close.return_value = {"daily_candles": {}}
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
    )
    outcomes = bridge.process_after_poll(eval_time)
    assert outcomes.outcomes[0].deferred is True
    assert outcomes.outcomes[0].status != SchedulerRunStatus.FAILED


def test_market_event_job_names_for_subjobs() -> None:
    open_time = utc_dt(2024, 1, 16)
    assert daily_open_gap_job_name("BTC", open_time) == "me:do:gap:BTC:20240116T000000Z"
    assert daily_open_fill_job_name("BTC", open_time) == "me:do:fill:BTC:20240116T000000Z"
    assert daily_open_snapshot_job_name("BTC", open_time) == "me:do:snap:BTC:20240116T000000Z"
    event = MarketEvent(
        event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
        symbol="BTC",
        candle_open_time=open_time,
        provider_received_at=open_time,
    )
    assert market_event_job_name(event) == "me:do:BTC:20240116T000000Z"
