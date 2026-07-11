"""Market-data event detection and scheduler bridge for production lifecycle."""

from __future__ import annotations

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
from paper_trading.ids import format_utc_timestamp, scheduler_run_key
from paper_trading.lock import AdvisoryLock
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler import PaperTradingScheduler, SchedulerJobName
from paper_trading.scheduler_context import ProductionContextBuilder

logger = logging.getLogger(__name__)

DEFAULT_MAX_EVENTS_PER_POLL = 256


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


def market_event_job_name(event: MarketEvent) -> str:
    ts = format_utc_timestamp(event.candle_open_time)
    if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
        return f"market_event:daily_open:{event.symbol}:{ts}"
    if event.event_type == MarketEventType.DAILY_LIVE_UPDATE:
        low = event.observed_low
        assert low is not None
        return f"market_event:daily_live:{event.symbol}:{ts}:low:{format(low, 'f')}"
    if event.event_type == MarketEventType.DAILY_CLOSED:
        return f"market_event:daily_closed:{event.symbol}:{ts}"
    if event.event_type == MarketEventType.WEEKLY_CLOSED:
        return f"market_event:weekly_closed:{event.symbol}:{ts}"
    if event.event_type == MarketEventType.MONTHLY_CLOSED:
        return f"market_event:monthly_closed:{event.symbol}:{ts}"
    raise ValueError(f"unknown event type: {event.event_type}")


@dataclass
class SymbolSeriesTracker:
    daily_open_time: datetime | None = None
    daily_observed_low: Decimal | None = None
    daily_closed_open_time: datetime | None = None
    weekly_closed_open_time: datetime | None = None
    monthly_closed_open_time: datetime | None = None


@dataclass(frozen=True)
class EventProcessOutcome:
    event: MarketEvent
    job_name: str
    status: SchedulerRunStatus
    skipped: bool
    error: str | None = None


@dataclass
class MarketEventDetector:
    """Detect lifecycle events by diffing candle repository state."""

    symbols: tuple[str, ...]
    _trackers: dict[str, SymbolSeriesTracker] = field(default_factory=dict)

    def detect(
        self,
        repository: InMemoryCandleRepository,
        evaluation_time: datetime,
    ) -> tuple[MarketEvent, ...]:
        evaluation_time = ensure_utc(evaluation_time)
        events: list[MarketEvent] = []
        for symbol in self.symbols:
            events.extend(self._detect_symbol(repository, symbol, evaluation_time))
        return tuple(events)

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
            events.extend(
                self._detect_daily(tracker, daily, evaluation_time)
            )

        weekly = repository.get_latest(ms, MarketTimeframe.WEEKLY)
        if weekly is not None:
            events.extend(
                self._detect_higher_close(
                    tracker,
                    weekly,
                    evaluation_time,
                    MarketEventType.WEEKLY_CLOSED,
                    "weekly_closed_open_time",
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
                    "monthly_closed_open_time",
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

        if tracker.daily_open_time != open_time:
            tracker.daily_open_time = open_time
            tracker.daily_observed_low = candle.low
            events.append(
                MarketEvent(
                    event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
                    symbol=candle.symbol.value,
                    candle_open_time=open_time,
                    provider_received_at=evaluation_time,
                )
            )
        elif tracker.daily_observed_low != candle.low and not candle.is_closed:
            tracker.daily_observed_low = candle.low
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
        if closed and tracker.daily_closed_open_time != open_time:
            tracker.daily_closed_open_time = open_time
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
        setattr(tracker, tracker_field, open_time)
        return [
            MarketEvent(
                event_type=event_type,
                symbol=candle.symbol.value,
                candle_open_time=open_time,
                provider_received_at=evaluation_time,
            )
        ]


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

    def __post_init__(self) -> None:
        if self.detector is None:
            self.detector = MarketEventDetector(symbols=self.config.symbols)

    @property
    def queue_overflow(self) -> bool:
        return self._queue_overflow

    def process_after_poll(self, evaluation_time: datetime) -> tuple[EventProcessOutcome, ...]:
        evaluation_time = ensure_utc(evaluation_time)
        if not self.market_data_ready():
            return ()
        if not self.advisory_lock.held:
            return ()
        if self._session_unhealthy():
            return ()

        assert self.detector is not None
        events = self.detector.detect(self.candle_repository, evaluation_time)
        if len(events) > self.max_events_per_poll:
            self._queue_overflow = True
            logger.error(
                "market_event_queue_overflow",
                extra={"count": len(events), "max": self.max_events_per_poll},
            )
            return (
                EventProcessOutcome(
                    event=events[0],
                    job_name="market_event:overflow",
                    status=SchedulerRunStatus.FAILED,
                    skipped=False,
                    error="event_queue_overflow",
                ),
            )

        outcomes: list[EventProcessOutcome] = []
        for event in events:
            outcomes.append(self._process_event(event, evaluation_time))
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

    def _process_event(
        self,
        event: MarketEvent,
        evaluation_time: datetime,
    ) -> EventProcessOutcome:
        job_name = market_event_job_name(event)
        scheduled_for = event.scheduled_for

        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is not None and existing.status == SchedulerRunStatus.COMPLETED:
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

        started = self.clock.now()
        with transaction_scope(self.repository.session):
            run, created = self.repository.insert_or_get_scheduler_run(
                SchedulerRunRow(
                    run_id=uuid4(),
                    job_name=job_name,
                    scheduled_for=scheduled_for,
                    started_at=started,
                    status=SchedulerRunStatus.RUNNING.value,
                    idempotency_key=scheduler_run_key(job_name, scheduled_for),
                )
            )
            if not created and run.status == SchedulerRunStatus.COMPLETED.value:
                return EventProcessOutcome(
                    event=event,
                    job_name=job_name,
                    status=SchedulerRunStatus.COMPLETED,
                    skipped=True,
                )

        try:
            if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
                self._handle_daily_open(event, evaluation_time)
            elif event.event_type == MarketEventType.DAILY_LIVE_UPDATE:
                self._handle_daily_live(event, evaluation_time)
            elif event.event_type == MarketEventType.DAILY_CLOSED:
                self._handle_daily_closed(event, evaluation_time)
            else:
                raise ValueError(f"unsupported event: {event.event_type}")

            self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
            return EventProcessOutcome(
                event=event,
                job_name=job_name,
                status=SchedulerRunStatus.COMPLETED,
                skipped=False,
            )
        except Exception as exc:
            logger.exception("market_event_processing_failed", extra={"job_name": job_name})
            self._complete_market_event(
                job_name, scheduled_for, SchedulerRunStatus.FAILED, str(exc)
            )
            return EventProcessOutcome(
                event=event,
                job_name=job_name,
                status=SchedulerRunStatus.FAILED,
                skipped=False,
                error=str(exc),
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
        self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
        return EventProcessOutcome(
            event=event,
            job_name=job_name,
            status=SchedulerRunStatus.COMPLETED,
            skipped=False,
        )

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

    def _latest_daily(self, symbol: str) -> NormalizedCandle | None:
        return self.candle_repository.get_latest(
            MarketSymbol(symbol),
            MarketTimeframe.DAILY,
        )

    def _handle_daily_open(self, event: MarketEvent, evaluation_time: datetime) -> None:
        candle = self._latest_daily(event.symbol)
        if candle is None or candle.open_time != event.candle_open_time:
            raise ValueError("daily open candle missing at processing time")

        fill_contexts, stop_context = self.context_builder.build_open_contexts(
            event.symbol,
            candle,
            evaluation_time,
        )
        if fill_contexts is None or stop_context is None:
            raise ValueError(f"missing open context for {event.symbol}")

        self.scheduler.register_fill_contexts(fill_contexts)
        self.scheduler.register_stop_context(**stop_context)
        outcomes = self.scheduler.run_daily_open_sequence(
            scheduled_for=event.candle_open_time,
            advisory_lock=self.advisory_lock,
        )
        failed = [o for o in outcomes if o.status == SchedulerRunStatus.FAILED]
        if failed:
            raise RuntimeError(f"daily open sequence failed: {failed[0].error}")

    def _handle_daily_live(self, event: MarketEvent, evaluation_time: datetime) -> None:
        candle = self._latest_daily(event.symbol)
        if candle is None or candle.open_time != event.candle_open_time:
            raise ValueError("daily live candle missing at processing time")
        if event.observed_low is not None and candle.low != event.observed_low:
            candle = candle.model_copy(update={"low": event.observed_low})

        stop_context = self.context_builder.build_intraday_stop_context(event.symbol, candle)
        if stop_context is None:
            raise ValueError(f"missing intraday stop context for {event.symbol}")

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
            raise ValueError("daily closed candle missing at processing time")

        due = candle.close_time + timedelta(seconds=self.config.evaluation_delay_seconds)
        if self.clock.now() < due:
            raise RuntimeError("daily evaluation not due")

        eval_time = due
        eval_context = self.context_builder.build_evaluation_context(event.symbol, eval_time)
        if eval_context is None:
            raise ValueError(f"missing evaluation context for {event.symbol}")

        stop_context = self.context_builder.build_stop_context_for_close(
            event.symbol,
            eval_time,
        )
        if stop_context is None:
            raise ValueError(f"missing trailing stop context for {event.symbol}")

        self.scheduler.register_evaluation_context(**eval_context)
        self.scheduler.register_stop_context(**stop_context)
        outcomes = self.scheduler.run_daily_close_sequence(
            scheduled_for=candle.close_time,
            advisory_lock=self.advisory_lock,
        )
        failed = [o for o in outcomes if o.status == SchedulerRunStatus.FAILED]
        if failed:
            raise RuntimeError(f"daily close sequence failed: {failed[0].error}")
