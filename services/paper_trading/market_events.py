"""Market-data event detection and scheduler bridge for production lifecycle."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import ensure_utc, is_candle_closed
from sqlalchemy import text
from sqlalchemy.orm import Session

from paper_trading.clock import Clock
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.db.transaction import transaction_scope
from paper_trading.enums import SchedulerRunStatus
from paper_trading.ids import scheduler_run_key
from paper_trading.lock import AdvisoryLock
from paper_trading.market_event_errors import (
    DailyEvaluationNotDue,
    FillNotDue,
    MarketEventProcessingError,
    PermanentConfigurationFailure,
    RetryableContextNotReady,
)
from paper_trading.models import SchedulerRun
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler import JobRunOutcome, PaperTradingScheduler, SchedulerJobName
from paper_trading.scheduler_context import ProductionContextBuilder

logger = logging.getLogger(__name__)

DEFAULT_MAX_EVENTS_PER_POLL = 256

_SYMBOL_ORDER = {"BTC": 0, "ETH": 1, "SOL": 2}
_EVENT_ORDER = {
    "DAILY_OPEN_AVAILABLE": 0,
    "DAILY_LIVE_UPDATE": 1,
    "DAILY_CLOSED": 2,
    "WEEKLY_CLOSED": 3,
    "MONTHLY_CLOSED": 4,
}


class MarketEventType(StrEnum):
    DAILY_OPEN_AVAILABLE = "DAILY_OPEN_AVAILABLE"
    DAILY_LIVE_UPDATE = "DAILY_LIVE_UPDATE"
    DAILY_CLOSED = "DAILY_CLOSED"
    WEEKLY_CLOSED = "WEEKLY_CLOSED"
    MONTHLY_CLOSED = "MONTHLY_CLOSED"


@dataclass(frozen=True)
class MarketEvent:
    event_type: MarketEventType
    symbol: str
    candle_open_time: datetime
    provider_received_at: datetime
    observed_low: Decimal | None = None

    @property
    def scheduled_for(self) -> datetime:
        return self.candle_open_time


def _compact_timestamp(dt: datetime) -> str:
    normalized = ensure_utc(dt)
    return normalized.strftime("%Y%m%dT%H%M%SZ")


def market_event_job_name(event: MarketEvent) -> str:
    ts = _compact_timestamp(event.candle_open_time)
    if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
        return f"me:do:{event.symbol}:{ts}"
    if event.event_type == MarketEventType.DAILY_LIVE_UPDATE:
        low = event.observed_low
        assert low is not None
        low_digest = hashlib.sha256(format(low, "f").encode()).hexdigest()[:12]
        return f"me:dl:{event.symbol}:{ts}:{low_digest}"
    if event.event_type == MarketEventType.DAILY_CLOSED:
        return f"me:dc:{event.symbol}:{ts}"
    if event.event_type == MarketEventType.WEEKLY_CLOSED:
        return f"me:wc:{event.symbol}:{ts}"
    if event.event_type == MarketEventType.MONTHLY_CLOSED:
        return f"me:mc:{event.symbol}:{ts}"
    raise ValueError(f"unknown event type: {event.event_type}")


def daily_open_gap_job_name(symbol: str, open_time: datetime) -> str:
    return f"me:do:gap:{symbol}:{_compact_timestamp(open_time)}"


def daily_open_fill_job_name(symbol: str, open_time: datetime) -> str:
    return f"me:do:fill:{symbol}:{_compact_timestamp(open_time)}"


def daily_open_snapshot_job_name(symbol: str, open_time: datetime) -> str:
    return f"me:do:snap:{symbol}:{_compact_timestamp(open_time)}"


@dataclass
class SymbolSeriesTracker:
    """Acknowledged event state — updated only after terminal bridge success."""

    daily_open_ack_time: datetime | None = None
    daily_live_ack_low: Decimal | None = None
    daily_closed_ack_time: datetime | None = None
    weekly_closed_ack_time: datetime | None = None
    monthly_closed_ack_time: datetime | None = None


@dataclass(frozen=True)
class EventProcessOutcome:
    event: MarketEvent
    job_name: str
    status: SchedulerRunStatus
    skipped: bool
    error: str | None = None
    deferred: bool = False
    retryable: bool = False


@dataclass
class MarketEventDetector:
    """Detect lifecycle event candidates without irreversible consumption."""

    symbols: tuple[str, ...]
    evaluation_delay_seconds: int = 5
    _trackers: dict[str, SymbolSeriesTracker] = field(default_factory=dict)

    def detect(
        self,
        repository: InMemoryCandleRepository,
        evaluation_time: datetime,
    ) -> tuple[MarketEvent, ...]:
        return self.detect_candidates(repository, evaluation_time)

    def detect_candidates(
        self,
        repository: InMemoryCandleRepository,
        evaluation_time: datetime,
    ) -> tuple[MarketEvent, ...]:
        evaluation_time = ensure_utc(evaluation_time)
        events: list[MarketEvent] = []
        for symbol in self.symbols:
            events.extend(self._detect_symbol(repository, symbol, evaluation_time))
        return tuple(events)

    def acknowledge_completed(self, event: MarketEvent) -> None:
        tracker = self._tracker(event.symbol)
        open_time = ensure_utc(event.candle_open_time)
        if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
            tracker.daily_open_ack_time = open_time
            tracker.daily_live_ack_low = event.observed_low
        elif event.event_type == MarketEventType.DAILY_LIVE_UPDATE:
            tracker.daily_live_ack_low = event.observed_low
        elif event.event_type == MarketEventType.DAILY_CLOSED:
            tracker.daily_closed_ack_time = open_time
        elif event.event_type == MarketEventType.WEEKLY_CLOSED:
            tracker.weekly_closed_ack_time = open_time
        elif event.event_type == MarketEventType.MONTHLY_CLOSED:
            tracker.monthly_closed_ack_time = open_time
        else:
            raise ValueError(f"unknown event type: {event.event_type}")

    def _tracker(self, symbol: str) -> SymbolSeriesTracker:
        if symbol not in self._trackers:
            self._trackers[symbol] = SymbolSeriesTracker()
        return self._trackers[symbol]

    def _detect_symbol(
        self,
        repository: InMemoryCandleRepository,
        symbol: str,
        evaluation_time: datetime,
    ) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        ms = MarketSymbol(symbol)
        tracker = self._tracker(symbol)

        daily = repository.get_latest(ms, MarketTimeframe.DAILY)
        if daily is not None:
            events.extend(self._detect_daily(tracker, daily, evaluation_time))

        weekly = repository.get_latest(ms, MarketTimeframe.WEEKLY)
        if weekly is not None:
            events.extend(
                self._detect_higher_close(
                    tracker,
                    weekly,
                    evaluation_time,
                    MarketEventType.WEEKLY_CLOSED,
                    "weekly_closed_ack_time",
                )
            )

        monthly = repository.get_latest(ms, MarketTimeframe.MONTHLY)
        if monthly is not None:
            events.extend(
                self._detect_higher_close(
                    tracker,
                    monthly,
                    evaluation_time,
                    MarketEventType.MONTHLY_CLOSED,
                    "monthly_closed_ack_time",
                )
            )

        return events

    def _detect_daily(
        self,
        tracker: SymbolSeriesTracker,
        candle: NormalizedCandle,
        evaluation_time: datetime,
    ) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        open_time = ensure_utc(candle.open_time)

        if not candle.is_closed and tracker.daily_open_ack_time != open_time:
            events.append(
                MarketEvent(
                    event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
                    symbol=candle.symbol.value,
                    candle_open_time=open_time,
                    provider_received_at=evaluation_time,
                    observed_low=candle.low,
                )
            )
        elif (
            tracker.daily_open_ack_time == open_time
            and not candle.is_closed
            and tracker.daily_live_ack_low != candle.low
        ):
            events.append(
                MarketEvent(
                    event_type=MarketEventType.DAILY_LIVE_UPDATE,
                    symbol=candle.symbol.value,
                    candle_open_time=open_time,
                    provider_received_at=evaluation_time,
                    observed_low=candle.low,
                )
            )

        closed = is_candle_closed(candle.close_time, evaluation_time) and candle.is_closed
        due = candle.close_time + timedelta(seconds=self.evaluation_delay_seconds)
        if (
            closed
            and evaluation_time >= due
            and tracker.daily_closed_ack_time != open_time
        ):
            events.append(
                MarketEvent(
                    event_type=MarketEventType.DAILY_CLOSED,
                    symbol=candle.symbol.value,
                    candle_open_time=open_time,
                    provider_received_at=evaluation_time,
                )
            )
        return events

    def _detect_higher_close(
        self,
        tracker: SymbolSeriesTracker,
        candle: NormalizedCandle,
        evaluation_time: datetime,
        event_type: MarketEventType,
        tracker_field: str,
    ) -> list[MarketEvent]:
        open_time = ensure_utc(candle.open_time)
        if not is_candle_closed(candle.close_time, evaluation_time) or not candle.is_closed:
            return []
        last = getattr(tracker, tracker_field)
        if last == open_time:
            return []
        return [
            MarketEvent(
                event_type=event_type,
                symbol=candle.symbol.value,
                candle_open_time=open_time,
                provider_received_at=evaluation_time,
            )
        ]


def _sort_market_events(events: list[MarketEvent]) -> list[MarketEvent]:
    return sorted(
        events,
        key=lambda event: (
            _SYMBOL_ORDER.get(event.symbol, 99),
            _EVENT_ORDER.get(event.event_type.value, 99),
            event.candle_open_time,
        ),
    )


@dataclass
class MarketEventBridge:
    """Bridge Hyperliquid market data events to scheduler lifecycle jobs."""

    repository: PaperTradingRepository
    candle_repository: InMemoryCandleRepository
    scheduler: PaperTradingScheduler
    context_builder: ProductionContextBuilder
    config: PaperTradingConfig
    clock: Clock
    advisory_lock: AdvisoryLock
    market_data_ready: Callable[[], bool]
    detector: MarketEventDetector | None = None
    max_events_per_poll: int = DEFAULT_MAX_EVENTS_PER_POLL
    _queue_overflow: bool = field(default=False, init=False)
    _deferred_events: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.detector is None:
            self.detector = MarketEventDetector(
                symbols=self.config.symbols,
                evaluation_delay_seconds=self.config.evaluation_delay_seconds,
            )

    @property
    def queue_overflow(self) -> bool:
        return self._queue_overflow

    @property
    def deferred_events(self) -> bool:
        return self._deferred_events

    @property
    def has_event_backlog(self) -> bool:
        return self._queue_overflow or self._deferred_events

    def process_after_poll(self, evaluation_time: datetime) -> tuple[EventProcessOutcome, ...]:
        evaluation_time = ensure_utc(evaluation_time)
        self._deferred_events = False
        if not self.market_data_ready():
            return ()
        if not self.advisory_lock.held:
            return ()
        if self._session_unhealthy():
            return ()

        assert self.detector is not None
        candidates = list(
            self.detector.detect_candidates(self.candle_repository, evaluation_time)
        )
        candidates = _sort_market_events(candidates)
        total_candidates = len(candidates)
        self._queue_overflow = total_candidates > self.max_events_per_poll
        if self._queue_overflow:
            logger.error(
                "market_event_queue_overflow",
                extra={"count": total_candidates, "max": self.max_events_per_poll},
            )
            candidates = candidates[: self.max_events_per_poll]

        outcomes: list[EventProcessOutcome] = []
        for event in candidates:
            outcome = self._process_event(event, evaluation_time)
            if outcome.status == SchedulerRunStatus.COMPLETED and not outcome.skipped:
                self.detector.acknowledge_completed(event)
            if outcome.deferred or outcome.retryable:
                self._deferred_events = True
            outcomes.append(outcome)
        return tuple(outcomes)

    def _session_unhealthy(self) -> bool:
        session: Session = self.repository.session
        try:
            if not session.is_active:
                return True
            session.execute(text("SELECT 1"))
            return False
        except Exception:
            logger.exception("market_event_db_unhealthy")
            return True

    def _persisted_outcome(
        self,
        event: MarketEvent,
        job_name: str,
        scheduled_for: datetime,
        *,
        skipped: bool,
        deferred: bool = False,
        retryable: bool = False,
    ) -> EventProcessOutcome:
        run = self.repository.get_scheduler_run(job_name, scheduled_for)
        if run is None and not deferred:
            raise RuntimeError(f"scheduler run missing after processing: {job_name}")
        status = run.status if run is not None else SchedulerRunStatus.SKIPPED
        error = run.error if run is not None else None
        return EventProcessOutcome(
            event=event,
            job_name=job_name,
            status=status,
            skipped=skipped,
            error=error,
            deferred=deferred,
            retryable=retryable,
        )

    def _deferred_outcome(
        self,
        event: MarketEvent,
        *,
        error: MarketEventProcessingError,
    ) -> EventProcessOutcome:
        return EventProcessOutcome(
            event=event,
            job_name=market_event_job_name(event),
            status=SchedulerRunStatus.SKIPPED,
            skipped=True,
            error=error.code,
            deferred=True,
            retryable=True,
        )

    def _ensure_scheduler_run(
        self,
        job_name: str,
        scheduled_for: datetime,
    ) -> tuple[SchedulerRun, bool]:
        started = self.clock.now()
        with transaction_scope(self.repository.session):
            return self.repository.insert_or_get_scheduler_run(
                SchedulerRunRow(
                    run_id=uuid4(),
                    job_name=job_name,
                    scheduled_for=scheduled_for,
                    started_at=started,
                    status=SchedulerRunStatus.RUNNING.value,
                    idempotency_key=scheduler_run_key(job_name, scheduled_for),
                )
            )

    def _process_event(
        self,
        event: MarketEvent,
        evaluation_time: datetime,
    ) -> EventProcessOutcome:
        job_name = market_event_job_name(event)
        scheduled_for = event.scheduled_for

        if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
            return self._process_daily_open(event, evaluation_time)

        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is not None and existing.status == SchedulerRunStatus.COMPLETED:
            if self.detector is not None:
                self.detector.acknowledge_completed(event)
            return EventProcessOutcome(
                event=event,
                job_name=job_name,
                status=SchedulerRunStatus.COMPLETED,
                skipped=True,
            )

        if event.event_type in {
            MarketEventType.WEEKLY_CLOSED,
            MarketEventType.MONTHLY_CLOSED,
        }:
            return self._complete_marker_event(event, job_name, scheduled_for)

        run, created = self._ensure_scheduler_run(job_name, scheduled_for)
        if not created and run.status == SchedulerRunStatus.COMPLETED.value:
            if self.detector is not None:
                self.detector.acknowledge_completed(event)
            return EventProcessOutcome(
                event=event,
                job_name=job_name,
                status=SchedulerRunStatus.COMPLETED,
                skipped=True,
            )

        try:
            if event.event_type == MarketEventType.DAILY_LIVE_UPDATE:
                self._handle_daily_live(event, evaluation_time)
            elif event.event_type == MarketEventType.DAILY_CLOSED:
                self._handle_daily_closed(event, evaluation_time)
            else:
                raise ValueError(f"unsupported event: {event.event_type}")

            self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
            return self._persisted_outcome(
                event, job_name, scheduled_for, skipped=False
            )
        except RetryableContextNotReady as exc:
            logger.warning(
                "market_event_deferred",
                extra={"job_name": job_name, "error": exc.code},
            )
            return self._deferred_outcome(event, error=exc)
        except DailyEvaluationNotDue as exc:
            return self._deferred_outcome(event, error=exc)
        except PermanentConfigurationFailure as exc:
            logger.exception(
                "market_event_processing_failed",
                extra={"job_name": job_name, "error": exc.code},
            )
            self._complete_market_event(
                job_name, scheduled_for, SchedulerRunStatus.FAILED, exc.code
            )
            return self._persisted_outcome(
                event, job_name, scheduled_for, skipped=False
            )
        except Exception as exc:
            logger.exception("market_event_processing_failed", extra={"job_name": job_name})
            self._complete_market_event(
                job_name, scheduled_for, SchedulerRunStatus.FAILED, str(exc)
            )
            return self._persisted_outcome(
                event, job_name, scheduled_for, skipped=False
            )

    def _process_daily_open(
        self,
        event: MarketEvent,
        evaluation_time: datetime,
    ) -> EventProcessOutcome:
        scheduled_for = event.scheduled_for
        if self._daily_open_terminal_complete(event.symbol, scheduled_for):
            if self.detector is not None:
                self.detector.acknowledge_completed(event)
            return EventProcessOutcome(
                event=event,
                job_name=market_event_job_name(event),
                status=SchedulerRunStatus.COMPLETED,
                skipped=True,
            )
        try:
            self._handle_daily_open(event, evaluation_time)
            return EventProcessOutcome(
                event=event,
                job_name=market_event_job_name(event),
                status=SchedulerRunStatus.COMPLETED,
                skipped=False,
            )
        except FillNotDue as exc:
            return self._deferred_outcome(event, error=exc)
        except RetryableContextNotReady as exc:
            logger.warning(
                "daily_open_deferred",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            return self._deferred_outcome(event, error=exc)
        except PermanentConfigurationFailure as exc:
            job_name = market_event_job_name(event)
            self._ensure_scheduler_run(job_name, scheduled_for)
            self._complete_market_event(
                job_name, scheduled_for, SchedulerRunStatus.FAILED, exc.code
            )
            return self._persisted_outcome(event, job_name, scheduled_for, skipped=False)

    def _daily_open_terminal_complete(self, symbol: str, scheduled_for: datetime) -> bool:
        gap = self.repository.get_scheduler_run(
            daily_open_gap_job_name(symbol, scheduled_for), scheduled_for
        )
        fill = self.repository.get_scheduler_run(
            daily_open_fill_job_name(symbol, scheduled_for), scheduled_for
        )
        snap = self.repository.get_scheduler_run(
            daily_open_snapshot_job_name(symbol, scheduled_for), scheduled_for
        )
        required = [gap, fill, snap]
        if self.config.fill_delay_seconds <= 0:
            return all(
                run is not None and run.status == SchedulerRunStatus.COMPLETED for run in required
            )
        return (
            gap is not None
            and gap.status == SchedulerRunStatus.COMPLETED
            and fill is not None
            and fill.status == SchedulerRunStatus.COMPLETED
            and snap is not None
            and snap.status == SchedulerRunStatus.COMPLETED
        )

    def _complete_marker_event(
        self,
        event: MarketEvent,
        job_name: str,
        scheduled_for: datetime,
    ) -> EventProcessOutcome:
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is not None and existing.status == SchedulerRunStatus.COMPLETED:
            return EventProcessOutcome(
                event=event,
                job_name=job_name,
                status=SchedulerRunStatus.COMPLETED,
                skipped=True,
            )

        run, created = self._ensure_scheduler_run(job_name, scheduled_for)
        if not created and run.status == SchedulerRunStatus.COMPLETED.value:
            return EventProcessOutcome(
                event=event,
                job_name=job_name,
                status=SchedulerRunStatus.COMPLETED,
                skipped=True,
            )

        self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
        return self._persisted_outcome(event, job_name, scheduled_for, skipped=not created)

    def _complete_market_event(
        self,
        job_name: str,
        scheduled_for: datetime,
        status: SchedulerRunStatus,
        error: str | None,
    ) -> None:
        with transaction_scope(self.repository.session):
            self.repository.complete_scheduler_run(
                job_name=job_name,
                scheduled_for=scheduled_for,
                status=status,
                completed_at=self.clock.now(),
                error=error,
            )

    def _run_open_subjob(
        self,
        job_name: str,
        scheduled_for: datetime,
        runner: Callable[[], tuple[JobRunOutcome, ...]],
    ) -> None:
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is not None and existing.status == SchedulerRunStatus.COMPLETED:
            return

        self._ensure_scheduler_run(job_name, scheduled_for)
        try:
            outcomes = runner()
            failed = [o for o in outcomes if o.status == SchedulerRunStatus.FAILED]
            if failed:
                raise RuntimeError(failed[0].error or "open subjob failed")
            self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
        except Exception as exc:
            self._complete_market_event(
                job_name, scheduled_for, SchedulerRunStatus.FAILED, str(exc)
            )
            raise

    def _latest_daily(self, symbol: str) -> NormalizedCandle | None:
        return self.candle_repository.get_latest(
            MarketSymbol(symbol),
            MarketTimeframe.DAILY,
        )

    def _handle_daily_open(self, event: MarketEvent, evaluation_time: datetime) -> None:
        candle = self._latest_daily(event.symbol)
        if candle is None or candle.open_time != event.candle_open_time:
            raise RetryableContextNotReady("daily open candle missing at processing time")

        fill_contexts, stop_context = self.context_builder.build_open_contexts(
            event.symbol,
            candle,
            evaluation_time,
        )
        self.scheduler.register_fill_contexts(fill_contexts)
        self.scheduler.register_stop_context(**stop_context)

        scheduled_for = event.candle_open_time
        gap_job = daily_open_gap_job_name(event.symbol, scheduled_for)
        fill_job = daily_open_fill_job_name(event.symbol, scheduled_for)
        snap_job = daily_open_snapshot_job_name(event.symbol, scheduled_for)

        self._run_open_subjob(
            gap_job,
            scheduled_for,
            lambda: self.scheduler.run_daily_open_gap_stop(
                scheduled_for=scheduled_for,
                advisory_lock=self.advisory_lock,
            ),
        )

        fill_due = self.clock.now() >= scheduled_for + timedelta(
            seconds=self.config.fill_delay_seconds
        )
        if not fill_due:
            raise FillNotDue()

        self._run_open_subjob(
            fill_job,
            scheduled_for,
            lambda: self.scheduler.run_daily_open_fill(
                scheduled_for=scheduled_for,
                advisory_lock=self.advisory_lock,
            ),
        )
        self._run_open_subjob(
            snap_job,
            scheduled_for,
            lambda: self.scheduler.run_daily_open_snapshot(
                scheduled_for=scheduled_for,
                advisory_lock=self.advisory_lock,
            ),
        )

    def _handle_daily_live(self, event: MarketEvent, evaluation_time: datetime) -> None:
        candle = self._latest_daily(event.symbol)
        if candle is None or candle.open_time != event.candle_open_time:
            raise RetryableContextNotReady("daily live candle missing at processing time")
        if event.observed_low is not None and candle.low != event.observed_low:
            candle = candle.model_copy(update={"low": event.observed_low})

        stop_context = self.context_builder.build_intraday_stop_context(event.symbol, candle)
        self.scheduler.register_stop_context(**stop_context)
        outcome = self.scheduler.run_job(
            SchedulerJobName.INTRADAY_STOP_PROCESSING,
            scheduled_for=event.candle_open_time,
        )
        if outcome.status == SchedulerRunStatus.FAILED:
            raise RuntimeError(outcome.error or "intraday stop processing failed")

    def _handle_daily_closed(self, event: MarketEvent, evaluation_time: datetime) -> None:
        candle = self._latest_daily(event.symbol)
        if candle is None or candle.open_time != event.candle_open_time:
            raise RetryableContextNotReady("daily closed candle missing at processing time")

        due = candle.close_time + timedelta(seconds=self.config.evaluation_delay_seconds)
        if self.clock.now() < due:
            raise DailyEvaluationNotDue()

        eval_time = due
        eval_context = self.context_builder.build_evaluation_context(event.symbol, eval_time)
        stop_context = self.context_builder.build_stop_context_for_close(
            event.symbol,
            eval_time,
        )
        self.scheduler.register_evaluation_context(**eval_context)
        self.scheduler.register_stop_context(**stop_context)
        outcomes = self.scheduler.run_daily_close_sequence(
            scheduled_for=candle.close_time,
            advisory_lock=self.advisory_lock,
        )
        failed = [o for o in outcomes if o.status == SchedulerRunStatus.FAILED]
        if failed:
            raise RuntimeError(f"daily close sequence failed: {failed[0].error}")
