"""Market-data event detection and scheduler bridge for production lifecycle."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

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
from paper_trading.event_fairness import (
    FairnessEvent,
    MarketEventGroupState,
    advance_group_rotation_cursor,
    eligible_group_keys,
    group_events,
    next_retry_at,
    ordered_group_keys,
)
from paper_trading.ids import scheduler_run_key
from paper_trading.lock import AdvisoryLock
from paper_trading.market_event_errors import (
    DailyEvaluationNotDue,
    DailyOpenSequenceFailure,
    FillNotDue,
    MarketEventProcessingError,
    PermanentConfigurationFailure,
    RetryableContextNotReady,
    RetryableSchedulerDeferred,
    is_permanent_configuration_error,
    is_retryable_market_event_error,
)
from paper_trading.models import SchedulerRun
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler import JobRunOutcome, PaperTradingScheduler, SchedulerJobName
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.scheduler_outcomes import is_terminal_job_success, require_successful_jobs

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


def market_event_recovery_job_name(event: MarketEvent, generation: int) -> str:
    ts = _compact_timestamp(event.candle_open_time)
    if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
        return f"me:do:recovery:{event.symbol}:{ts}:{generation}"
    if event.event_type == MarketEventType.DAILY_CLOSED:
        return f"me:dc:recovery:{event.symbol}:{ts}:{generation}"
    if event.event_type == MarketEventType.WEEKLY_CLOSED:
        return f"me:wc:recovery:{event.symbol}:{ts}:{generation}"
    if event.event_type == MarketEventType.MONTHLY_CLOSED:
        return f"me:mc:recovery:{event.symbol}:{ts}:{generation}"
    raise ValueError(f"recovery not supported for event type: {event.event_type}")


@dataclass(frozen=True)
class RecoveryContext:
    original_run_id: UUID
    original_job_name: str
    recovery_job_name: str
    recovery_run_id: UUID
    scheduled_for: datetime
    generation: int


@dataclass
class SymbolSeriesTracker:
    """Acknowledged event state — updated only after terminal bridge success."""

    daily_open_ack_time: datetime | None = None
    daily_open_terminal_failed_time: datetime | None = None
    daily_live_ack_low: Decimal | None = None
    daily_closed_ack_time: datetime | None = None
    daily_closed_terminal_failed_time: datetime | None = None
    weekly_closed_ack_time: datetime | None = None
    weekly_closed_terminal_failed_time: datetime | None = None
    monthly_closed_ack_time: datetime | None = None
    monthly_closed_terminal_failed_time: datetime | None = None


@dataclass(frozen=True)
class EventProcessOutcome:
    event: MarketEvent
    job_name: str
    status: SchedulerRunStatus
    skipped: bool
    error: str | None = None
    deferred: bool = False
    retryable: bool = False
    terminal_failed: bool = False


@dataclass(frozen=True)
class BridgePollResult:
    """Poll processing result — detector ack happens only after outer commit."""

    outcomes: tuple[EventProcessOutcome, ...]
    events_to_ack: tuple[MarketEvent, ...]
    events_terminal_failed: tuple[MarketEvent, ...]
    deferred_events: bool
    permanent_failures: tuple[EventProcessOutcome, ...]


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
            tracker.daily_open_terminal_failed_time = None
            tracker.daily_live_ack_low = event.observed_low
        elif event.event_type == MarketEventType.DAILY_LIVE_UPDATE:
            tracker.daily_live_ack_low = event.observed_low
        elif event.event_type == MarketEventType.DAILY_CLOSED:
            tracker.daily_closed_ack_time = open_time
            tracker.daily_closed_terminal_failed_time = None
        elif event.event_type == MarketEventType.WEEKLY_CLOSED:
            tracker.weekly_closed_ack_time = open_time
            tracker.weekly_closed_terminal_failed_time = None
        elif event.event_type == MarketEventType.MONTHLY_CLOSED:
            tracker.monthly_closed_ack_time = open_time
            tracker.monthly_closed_terminal_failed_time = None
        else:
            raise ValueError(f"unknown event type: {event.event_type}")

    def acknowledge_terminal_failed(self, event: MarketEvent) -> None:
        tracker = self._tracker(event.symbol)
        open_time = ensure_utc(event.candle_open_time)
        if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
            tracker.daily_open_terminal_failed_time = open_time
        elif event.event_type == MarketEventType.DAILY_CLOSED:
            tracker.daily_closed_terminal_failed_time = open_time
        elif event.event_type == MarketEventType.WEEKLY_CLOSED:
            tracker.weekly_closed_terminal_failed_time = open_time
        elif event.event_type == MarketEventType.MONTHLY_CLOSED:
            tracker.monthly_closed_terminal_failed_time = open_time
        else:
            raise ValueError(f"terminal failure ack unsupported for {event.event_type}")

    def clear_terminal_failed(self, event: MarketEvent) -> None:
        tracker = self._tracker(event.symbol)
        if event.event_type == MarketEventType.DAILY_OPEN_AVAILABLE:
            tracker.daily_open_terminal_failed_time = None
        elif event.event_type == MarketEventType.DAILY_CLOSED:
            tracker.daily_closed_terminal_failed_time = None
        elif event.event_type == MarketEventType.WEEKLY_CLOSED:
            tracker.weekly_closed_terminal_failed_time = None
        elif event.event_type == MarketEventType.MONTHLY_CLOSED:
            tracker.monthly_closed_terminal_failed_time = None
        else:
            raise ValueError(f"terminal failure clear unsupported for {event.event_type}")

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
            if tracker.daily_open_terminal_failed_time != open_time:
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
            and tracker.daily_closed_terminal_failed_time != open_time
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
        terminal_field = tracker_field.replace("_ack_time", "_terminal_failed_time")
        terminal_last = getattr(tracker, terminal_field)
        if last == open_time or terminal_last == open_time:
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
        key=_market_event_sort_key,
    )


def _market_event_sort_key(event: MarketEvent) -> tuple[int, int, datetime]:
    return (
        _SYMBOL_ORDER.get(event.symbol, 99),
        _EVENT_ORDER.get(event.event_type.value, 99),
        event.candle_open_time,
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
    _recovery_pending: dict[tuple[str, datetime], RecoveryContext] = field(
        default_factory=dict, init=False
    )

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

    @property
    def has_permanent_failures(self) -> bool:
        return bool(self.repository.list_permanent_configuration_failures())

    def process_after_poll(self, evaluation_time: datetime) -> BridgePollResult:
        evaluation_time = ensure_utc(evaluation_time)
        self._deferred_events = False
        if not self.market_data_ready():
            return BridgePollResult((), (), (), False, ())
        if not self.advisory_lock.held:
            return BridgePollResult((), (), (), False, ())
        if self._session_unhealthy():
            return BridgePollResult((), (), (), False, ())

        assert self.detector is not None
        candidates = list(
            self.detector.detect_candidates(self.candle_repository, evaluation_time)
        )
        candidates = _sort_market_events(candidates)
        total_candidates = len(candidates)
        grouped = group_events(cast(Sequence[FairnessEvent], candidates))
        all_group_keys = ordered_group_keys(grouped)
        raw_group_states = self.repository.list_market_event_group_states()
        group_states = (
            raw_group_states if isinstance(raw_group_states, dict) else {}
        )
        eligible_keys = eligible_group_keys(
            all_group_keys,
            evaluation_time=evaluation_time,
            group_states=group_states,
        )
        rotation_cursor = self.repository.get_fairness_group_rotation_cursor()
        if not isinstance(rotation_cursor, int):
            rotation_cursor = 0
        self._queue_overflow = total_candidates > self.max_events_per_poll
        if self._queue_overflow:
            logger.error(
                "market_event_queue_overflow",
                extra={"count": total_candidates, "max": self.max_events_per_poll},
            )

        outcomes: list[EventProcessOutcome] = []
        events_to_ack: list[MarketEvent] = []
        events_terminal_failed: list[MarketEvent] = []
        permanent_failures: list[EventProcessOutcome] = []
        processed_count = 0
        had_deferred = False
        groups_rotated = 0

        if eligible_keys:
            start_index = rotation_cursor % len(eligible_keys)
            for offset in range(len(eligible_keys)):
                if processed_count >= self.max_events_per_poll:
                    break
                group_key = eligible_keys[(start_index + offset) % len(eligible_keys)]
                group_candidates = cast(list[MarketEvent], grouped[group_key])
                groups_rotated += 1
                group_blocked = False
                for event in group_candidates:
                    if processed_count >= self.max_events_per_poll:
                        break
                    if group_blocked:
                        break
                    outcome = self._process_event(event, evaluation_time)
                    processed_count += 1
                    if self._should_ack(outcome):
                        events_to_ack.append(event)
                    if outcome.terminal_failed:
                        events_terminal_failed.append(event)
                        self._clear_group_fairness_state(group_key)
                    if outcome.deferred or outcome.retryable:
                        self._deferred_events = True
                        had_deferred = True
                        group_blocked = True
                        self._record_group_deferred(
                            event=event,
                            group_key=group_key,
                            evaluation_time=evaluation_time,
                            group_states=group_states,
                        )
                    elif outcome.status == SchedulerRunStatus.FAILED and not outcome.deferred:
                        permanent_failures.append(outcome)
                        self._clear_group_fairness_state(group_key)
                    elif outcome.status == SchedulerRunStatus.COMPLETED and not outcome.deferred:
                        self._clear_group_fairness_state(group_key)
                    outcomes.append(outcome)

        new_cursor = advance_group_rotation_cursor(
            cursor=rotation_cursor,
            eligible_group_count=len(eligible_keys),
            groups_rotated=groups_rotated,
            had_deferred=had_deferred,
        )
        self.repository.set_fairness_group_rotation_cursor(
            cursor=new_cursor,
            updated_at=evaluation_time,
        )

        return BridgePollResult(
            outcomes=tuple(outcomes),
            events_to_ack=tuple(events_to_ack),
            events_terminal_failed=tuple(events_terminal_failed),
            deferred_events=self._deferred_events,
            permanent_failures=tuple(permanent_failures),
        )

    def _record_group_deferred(
        self,
        *,
        event: MarketEvent,
        group_key: str,
        evaluation_time: datetime,
        group_states: dict[str, MarketEventGroupState],
    ) -> None:
        existing = group_states.get(group_key)
        defer_count = (existing.defer_count + 1) if existing is not None else 1
        retry_at = next_retry_at(
            evaluation_time=evaluation_time,
            defer_count=defer_count,
        )
        with transaction_scope(self.repository.session):
            self.repository.upsert_market_event_group_deferred(
                group_key=group_key,
                event_type=event.event_type.value,
                group_time=event.candle_open_time,
                next_attempt_at=retry_at,
                defer_count=defer_count,
                updated_at=evaluation_time,
            )
        group_states[group_key] = MarketEventGroupState(
            group_key=group_key,
            event_type=event.event_type.value,
            group_time=event.candle_open_time,
            next_attempt_at=retry_at,
            defer_count=defer_count,
        )

    def _clear_group_fairness_state(self, group_key: str) -> None:
        with transaction_scope(self.repository.session):
            self.repository.delete_market_event_group_state(group_key)

    def acknowledge_committed(self, events: tuple[MarketEvent, ...]) -> None:
        """Apply detector ack only after the outer session commit succeeded."""
        if not events or self.detector is None:
            return
        for event in events:
            self.detector.acknowledge_completed(event)

    def acknowledge_terminal_failed_committed(
        self,
        events: tuple[MarketEvent, ...],
    ) -> None:
        """Stop retry emission for permanently failed events after commit."""
        if not events or self.detector is None:
            return
        for event in events:
            self.detector.acknowledge_terminal_failed(event)

    def recover_permanent_configuration(self, event: MarketEvent) -> None:
        """Allow one controlled retry after configuration correction."""
        if not self.advisory_lock.held:
            raise RuntimeError("advisory lock required for permanent failure recovery")
        job_name = market_event_job_name(event)
        scheduled_for = event.scheduled_for
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is None or existing.status != SchedulerRunStatus.FAILED:
            raise ValueError(f"no recoverable permanent failure for {job_name}")
        if not is_permanent_configuration_error(existing.error):
            raise ValueError(f"scheduler run is not a permanent configuration failure: {job_name}")
        if existing.resolved_by_run_id is not None:
            raise ValueError(f"permanent failure already recovered for {job_name}")
        self.context_builder.validate_symbol_configuration(event.symbol)
        if self.detector is not None:
            self.detector.clear_terminal_failed(event)
        generation = self.repository.count_recovery_attempts(existing.run_id) + 1
        recovery_job_name = market_event_recovery_job_name(event, generation)
        attempt, _created = self.repository.create_recovery_attempt(
            original_run=existing,
            recovery_job_name=recovery_job_name,
            started_at=self.clock.now(),
        )
        self._recovery_pending[(job_name, scheduled_for)] = RecoveryContext(
            original_run_id=existing.run_id,
            original_job_name=job_name,
            recovery_job_name=recovery_job_name,
            recovery_run_id=attempt.run_id,
            scheduled_for=scheduled_for,
            generation=generation,
        )

    def _active_recovery_context(
        self,
        job_name: str,
        scheduled_for: datetime,
    ) -> RecoveryContext | None:
        key = (job_name, scheduled_for)
        pending = self._recovery_pending.get(key)
        if pending is not None:
            return pending
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is None:
            return None
        attempt = self.repository.get_active_recovery_attempt(existing.run_id)
        if attempt is None:
            return None
        context = RecoveryContext(
            original_run_id=existing.run_id,
            original_job_name=job_name,
            recovery_job_name=attempt.job_name,
            recovery_run_id=attempt.run_id,
            scheduled_for=scheduled_for,
            generation=self.repository.count_recovery_attempts(existing.run_id),
        )
        self._recovery_pending[key] = context
        return context

    def _terminal_failed_outcome(
        self,
        event: MarketEvent,
        job_name: str,
        scheduled_for: datetime,
        error: str | None,
    ) -> EventProcessOutcome:
        return EventProcessOutcome(
            event=event,
            job_name=job_name,
            status=SchedulerRunStatus.FAILED,
            skipped=True,
            error=error,
            terminal_failed=True,
        )

    def _maybe_short_circuit_permanent_failure(
        self,
        event: MarketEvent,
        job_name: str,
        scheduled_for: datetime,
    ) -> EventProcessOutcome | None:
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is None or existing.status != SchedulerRunStatus.FAILED:
            return None
        if not is_permanent_configuration_error(existing.error):
            return None
        if existing.resolved_by_run_id is not None:
            return None
        if self._active_recovery_context(job_name, scheduled_for) is not None:
            return None
        return self._terminal_failed_outcome(
            event,
            job_name,
            scheduled_for,
            existing.error,
        )

    def _mark_permanent_failure(
        self,
        event: MarketEvent,
        job_name: str,
        scheduled_for: datetime,
        exc: PermanentConfigurationFailure,
    ) -> EventProcessOutcome:
        self._complete_market_event(
            job_name, scheduled_for, SchedulerRunStatus.FAILED, exc.code
        )
        return EventProcessOutcome(
            event=event,
            job_name=job_name,
            status=SchedulerRunStatus.FAILED,
            skipped=False,
            error=exc.code,
            terminal_failed=True,
        )

    @staticmethod
    def _should_ack(outcome: EventProcessOutcome) -> bool:
        return (
            outcome.status == SchedulerRunStatus.COMPLETED
            and not outcome.deferred
            and not outcome.retryable
        )

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
        release_job_name: str | None = None,
    ) -> EventProcessOutcome:
        job_name = market_event_job_name(event)
        self._release_uncommitted_scheduler_run(
            release_job_name or job_name,
            event.scheduled_for,
            error=error,
        )
        return EventProcessOutcome(
            event=event,
            job_name=job_name,
            status=SchedulerRunStatus.SKIPPED,
            skipped=True,
            error=error.code,
            deferred=True,
            retryable=True,
        )

    def _persist_daily_open_failure_audit(
        self,
        *,
        event: MarketEvent,
        parent_job: str,
        scheduled_for: datetime,
        failure: DailyOpenSequenceFailure,
    ) -> None:
        self._fail_daily_open_parent(parent_job, scheduled_for, failure.message)
        if failure.subjob_name != parent_job:
            existing = self.repository.get_scheduler_run(failure.subjob_name, scheduled_for)
            if existing is None:
                self._ensure_scheduler_run(failure.subjob_name, scheduled_for)
            self._complete_market_event(
                failure.subjob_name,
                scheduled_for,
                SchedulerRunStatus.FAILED,
                failure.message,
            )

    def _execute_phased_daily_open(
        self,
        event: MarketEvent,
        evaluation_time: datetime,
    ) -> None:
        self._handle_daily_open(event, evaluation_time)

    def _execute_atomic_daily_open(
        self,
        event: MarketEvent,
        evaluation_time: datetime,
    ) -> None:
        self._execute_phased_daily_open(event, evaluation_time)

    def _fill_phase_due(self, scheduled_for: datetime) -> bool:
        due = scheduled_for + timedelta(seconds=self.config.fill_delay_seconds)
        return self.clock.now() >= due

    def _reactivate_recovery_attempt(
        self,
        recovery_job: str,
        scheduled_for: datetime,
    ) -> None:
        existing = self.repository.get_scheduler_run(recovery_job, scheduled_for)
        if existing is None:
            self._ensure_scheduler_run(recovery_job, scheduled_for)
            return
        if (
            existing.status == SchedulerRunStatus.SKIPPED
            and is_retryable_market_event_error(existing.error)
        ):
            with transaction_scope(self.repository.session):
                self.repository.reactivate_scheduler_run(
                    job_name=recovery_job,
                    scheduled_for=scheduled_for,
                    started_at=self.clock.now(),
                )
            return
        if existing.status != SchedulerRunStatus.RUNNING:
            self._ensure_scheduler_run(recovery_job, scheduled_for)

    def _fail_daily_open_parent(
        self,
        parent_job: str,
        scheduled_for: datetime,
        error: str,
    ) -> None:
        existing = self.repository.get_scheduler_run(parent_job, scheduled_for)
        if existing is not None and existing.status == SchedulerRunStatus.COMPLETED:
            return
        if existing is None:
            self._ensure_scheduler_run(parent_job, scheduled_for)
        self._complete_market_event(
            parent_job,
            scheduled_for,
            SchedulerRunStatus.FAILED,
            error,
        )

    def _release_uncommitted_scheduler_run(
        self,
        job_name: str,
        scheduled_for: datetime,
        *,
        error: MarketEventProcessingError | None = None,
    ) -> None:
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is None:
            return
        if existing.recovery_of_run_id is not None:
            assert error is not None
            with transaction_scope(self.repository.session):
                self.repository.complete_scheduler_run(
                    job_name=job_name,
                    scheduled_for=scheduled_for,
                    status=SchedulerRunStatus.SKIPPED,
                    completed_at=self.clock.now(),
                    error=error.code,
                )
            return
        with transaction_scope(self.repository.session):
            self.repository.delete_scheduler_run_if_running(
                job_name=job_name,
                scheduled_for=scheduled_for,
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

        short_circuit = self._maybe_short_circuit_permanent_failure(
            event, job_name, scheduled_for
        )
        if short_circuit is not None:
            return short_circuit

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

        run, created = self._ensure_scheduler_run(job_name, scheduled_for)
        if not created and run.status == SchedulerRunStatus.COMPLETED.value:
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
        except RetryableSchedulerDeferred as exc:
            logger.warning(
                "market_event_scheduler_deferred",
                extra={"job_name": job_name, "error": exc.code},
            )
            return self._deferred_outcome(event, error=exc)
        except DailyEvaluationNotDue as exc:
            return self._deferred_outcome(event, error=exc)
        except PermanentConfigurationFailure as exc:
            logger.error(
                "market_event_permanent_configuration_failure",
                extra={"job_name": job_name, "error": exc.code},
            )
            return self._mark_permanent_failure(event, job_name, scheduled_for, exc)
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
        parent_job = market_event_job_name(event)
        short_circuit = self._maybe_short_circuit_permanent_failure(
            event, parent_job, scheduled_for
        )
        if short_circuit is not None:
            return short_circuit
        recovery = self._active_recovery_context(parent_job, scheduled_for)
        if recovery is not None:
            return self._process_daily_open_recovery(event, evaluation_time, recovery)
        if self._daily_open_terminal_complete(event.symbol, scheduled_for):
            self._ensure_parent_run_completed(parent_job, scheduled_for)
            return self._persisted_outcome(
                event, parent_job, scheduled_for, skipped=True
            )
        self._ensure_scheduler_run(parent_job, scheduled_for)
        try:
            self._execute_atomic_daily_open(event, evaluation_time)
            self._complete_market_event(
                parent_job, scheduled_for, SchedulerRunStatus.COMPLETED, None
            )
            return self._persisted_outcome(
                event, parent_job, scheduled_for, skipped=False
            )
        except FillNotDue as exc:
            return self._deferred_outcome(event, error=exc)
        except RetryableContextNotReady as exc:
            logger.warning(
                "daily_open_deferred",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            return self._deferred_outcome(event, error=exc)
        except RetryableSchedulerDeferred as exc:
            logger.warning(
                "daily_open_scheduler_deferred",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            return self._deferred_outcome(event, error=exc)
        except PermanentConfigurationFailure as exc:
            logger.error(
                "daily_open_permanent_configuration_failure",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            return self._mark_permanent_failure(event, parent_job, scheduled_for, exc)
        except DailyOpenSequenceFailure as exc:
            logger.exception(
                "daily_open_processing_failed",
                extra={"symbol": event.symbol, "job_name": parent_job},
            )
            self._persist_daily_open_failure_audit(
                event=event,
                parent_job=parent_job,
                scheduled_for=scheduled_for,
                failure=exc,
            )
            return self._persisted_outcome(
                event, parent_job, scheduled_for, skipped=False
            )
        except Exception as exc:
            logger.exception(
                "daily_open_processing_failed",
                extra={"symbol": event.symbol, "job_name": parent_job},
            )
            failure = DailyOpenSequenceFailure(
                subjob_name=parent_job,
                message=str(exc),
            )
            self._persist_daily_open_failure_audit(
                event=event,
                parent_job=parent_job,
                scheduled_for=scheduled_for,
                failure=failure,
            )
            return self._persisted_outcome(
                event, parent_job, scheduled_for, skipped=False
            )

    def _process_daily_open_recovery(
        self,
        event: MarketEvent,
        evaluation_time: datetime,
        recovery: RecoveryContext,
    ) -> EventProcessOutcome:
        scheduled_for = recovery.scheduled_for
        recovery_job = recovery.recovery_job_name
        parent_job = recovery.original_job_name
        self._reactivate_recovery_attempt(recovery_job, scheduled_for)
        try:
            self._execute_atomic_daily_open(event, evaluation_time)
            self._complete_market_event(
                recovery_job, scheduled_for, SchedulerRunStatus.COMPLETED, None
            )
            self.repository.mark_run_resolved(
                original_run_id=recovery.original_run_id,
                recovery_run_id=recovery.recovery_run_id,
            )
            self._recovery_pending.pop((parent_job, scheduled_for), None)
            return EventProcessOutcome(
                event=event,
                job_name=parent_job,
                status=SchedulerRunStatus.COMPLETED,
                skipped=False,
            )
        except FillNotDue as exc:
            return self._deferred_outcome(
                event, error=exc, release_job_name=recovery_job
            )
        except RetryableContextNotReady as exc:
            logger.warning(
                "daily_open_recovery_deferred",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            return self._deferred_outcome(
                event, error=exc, release_job_name=recovery_job
            )
        except RetryableSchedulerDeferred as exc:
            logger.warning(
                "daily_open_recovery_scheduler_deferred",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            return self._deferred_outcome(
                event, error=exc, release_job_name=recovery_job
            )
        except PermanentConfigurationFailure as exc:
            logger.error(
                "daily_open_recovery_permanent_configuration_failure",
                extra={"symbol": event.symbol, "error": exc.code},
            )
            self._complete_market_event(
                recovery_job, scheduled_for, SchedulerRunStatus.FAILED, exc.code
            )
            self._recovery_pending.pop((parent_job, scheduled_for), None)
            return EventProcessOutcome(
                event=event,
                job_name=parent_job,
                status=SchedulerRunStatus.FAILED,
                skipped=False,
                error=exc.code,
                terminal_failed=True,
            )
        except DailyOpenSequenceFailure as exc:
            logger.exception(
                "daily_open_recovery_failed",
                extra={"symbol": event.symbol, "recovery_job": recovery_job},
            )
            self._complete_market_event(
                recovery_job, scheduled_for, SchedulerRunStatus.FAILED, exc.message
            )
            self._recovery_pending.pop((parent_job, scheduled_for), None)
            return EventProcessOutcome(
                event=event,
                job_name=parent_job,
                status=SchedulerRunStatus.FAILED,
                skipped=False,
                error=exc.message,
            )
        except Exception as exc:
            logger.exception(
                "daily_open_recovery_failed",
                extra={"symbol": event.symbol, "recovery_job": recovery_job},
            )
            self._complete_market_event(
                recovery_job, scheduled_for, SchedulerRunStatus.FAILED, str(exc)
            )
            self._recovery_pending.pop((parent_job, scheduled_for), None)
            return EventProcessOutcome(
                event=event,
                job_name=parent_job,
                status=SchedulerRunStatus.FAILED,
                skipped=False,
                error=str(exc),
            )

    def _ensure_parent_run_completed(self, job_name: str, scheduled_for: datetime) -> None:
        existing = self.repository.get_scheduler_run(job_name, scheduled_for)
        if existing is not None and existing.status == SchedulerRunStatus.COMPLETED:
            return
        if existing is None:
            self._ensure_scheduler_run(job_name, scheduled_for)
        self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)

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
            require_successful_jobs(outcomes)
            if not all(is_terminal_job_success(outcome) for outcome in outcomes):
                raise RetryableSchedulerDeferred("scheduler_subjob_not_completed")
            self._complete_market_event(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
        except RetryableSchedulerDeferred:
            self._release_uncommitted_scheduler_run(
                job_name,
                scheduled_for,
                error=RetryableSchedulerDeferred("scheduler_subjob_not_completed"),
            )
            raise
        except DailyOpenSequenceFailure:
            raise
        except Exception as exc:
            raise DailyOpenSequenceFailure(subjob_name=job_name, message=str(exc)) from exc

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

        with transaction_scope(self.repository.session):
            self._run_open_subjob(
                gap_job,
                scheduled_for,
                lambda: self.scheduler.run_daily_open_gap_stop(
                    scheduled_for=scheduled_for,
                    advisory_lock=self.advisory_lock,
                ),
            )

        if not self._fill_phase_due(scheduled_for):
            raise FillNotDue()

        with transaction_scope(self.repository.session):
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
        require_successful_jobs((outcome,))

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
        require_successful_jobs(outcomes)
