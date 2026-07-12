"""Deterministic internal scheduler for paper trading jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from paper_trading.clock import Clock, SystemClock
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.db.transaction import transaction_scope
from paper_trading.enums import SchedulerRunStatus
from paper_trading.evaluation import PaperEvaluationService
from paper_trading.execution import PaperFillService
from paper_trading.ids import scheduler_run_key
from paper_trading.lifecycle import (
    SYMBOL_PROCESSING_ORDER,
    FillProcessingContext,
    process_scheduled_intents_for_open,
)
from paper_trading.lock import AdvisoryLock
from paper_trading.models import SchedulerRun
from paper_trading.readiness import ReadinessService
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService
from paper_trading.stops import StopLifecycleService


class SchedulerJobName(StrEnum):
    READINESS_CHECK = "readiness_check"
    DAILY_SIGNAL_EVALUATION = "daily_signal_evaluation"
    NEXT_OPEN_FILL_PROCESSING = "next_open_fill_processing"
    DAILY_STOP_UPDATE = "daily_stop_update"
    STOP_TRIGGER_PROCESSING = "stop_trigger_processing"
    INTRADAY_STOP_PROCESSING = "intraday_stop_processing"
    FUNDING_PROCESSING = "funding_processing"
    PORTFOLIO_SNAPSHOT = "portfolio_snapshot"
    RUNTIME_HEARTBEAT = "runtime_heartbeat"


@dataclass(frozen=True)
class JobRunOutcome:
    job_name: str
    scheduled_for: datetime
    status: SchedulerRunStatus
    skipped: bool
    error: str | None = None


JobHandler = Callable[..., Any]


def _default_market_data_ready() -> bool:
    return False


class PaperTradingScheduler:
    """Idempotent scheduler with PostgreSQL advisory lock gating."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        config: PaperTradingConfig,
        *,
        evaluation_service: PaperEvaluationService,
        fill_service: PaperFillService,
        stop_service: StopLifecycleService,
        clock: Clock | None = None,
        readiness: ReadinessService | None = None,
        runtime: RuntimeService | None = None,
        market_data_ready: Callable[[], bool] | None = None,
    ) -> None:
        self._repo = repository
        self._config = config
        self._clock = clock or SystemClock()
        self._market_data_ready = market_data_ready or _default_market_data_ready
        self._evaluation = evaluation_service
        self._fills = fill_service
        self._stops = stop_service
        self._readiness = readiness or ReadinessService(repository, config, clock=clock)
        self._runtime = runtime or RuntimeService(repository, clock=clock)
        self._handlers: dict[str, JobHandler] = {
            SchedulerJobName.READINESS_CHECK: self._job_readiness_check,
            SchedulerJobName.DAILY_SIGNAL_EVALUATION: self._job_daily_signal_evaluation,
            SchedulerJobName.NEXT_OPEN_FILL_PROCESSING: self._job_next_open_fill_processing,
            SchedulerJobName.DAILY_STOP_UPDATE: self._job_daily_stop_update,
            SchedulerJobName.STOP_TRIGGER_PROCESSING: self._job_stop_trigger_processing,
            SchedulerJobName.INTRADAY_STOP_PROCESSING: self._job_intraday_stop_processing,
            SchedulerJobName.FUNDING_PROCESSING: self._job_funding_processing,
            SchedulerJobName.PORTFOLIO_SNAPSHOT: self._job_portfolio_snapshot,
            SchedulerJobName.RUNTIME_HEARTBEAT: self._job_runtime_heartbeat,
        }
        self._pending_evaluation: dict[str, Any] | None = None
        self._pending_fill_contexts: dict[str, FillProcessingContext] | None = None
        self._pending_stop_context: dict[str, Any] | None = None
        self._jobs_enabled = False

    @property
    def jobs_enabled(self) -> bool:
        return self._jobs_enabled

    def set_jobs_enabled(self, enabled: bool) -> None:
        self._jobs_enabled = enabled

    def register_evaluation_context(self, **kwargs: Any) -> None:
        self._pending_evaluation = kwargs

    def register_fill_contexts(self, contexts: dict[str, FillProcessingContext]) -> None:
        self._pending_fill_contexts = contexts

    def register_stop_context(self, **kwargs: Any) -> None:
        self._pending_stop_context = kwargs

    def run_daily_open_gap_stop(
        self,
        *,
        scheduled_for: datetime,
        advisory_lock: AdvisoryLock,
        cycle_id: UUID | None = None,
    ) -> tuple[JobRunOutcome, ...]:
        return self._run_open_subsequence(
            scheduled_for=scheduled_for,
            advisory_lock=advisory_lock,
            cycle_id=cycle_id,
            jobs=(SchedulerJobName.STOP_TRIGGER_PROCESSING,),
        )

    def run_daily_open_fill(
        self,
        *,
        scheduled_for: datetime,
        advisory_lock: AdvisoryLock,
        cycle_id: UUID | None = None,
    ) -> tuple[JobRunOutcome, ...]:
        return self._run_open_subsequence(
            scheduled_for=scheduled_for,
            advisory_lock=advisory_lock,
            cycle_id=cycle_id,
            jobs=(SchedulerJobName.NEXT_OPEN_FILL_PROCESSING,),
        )

    def run_daily_open_snapshot(
        self,
        *,
        scheduled_for: datetime,
        advisory_lock: AdvisoryLock,
        cycle_id: UUID | None = None,
    ) -> tuple[JobRunOutcome, ...]:
        return self._run_open_subsequence(
            scheduled_for=scheduled_for,
            advisory_lock=advisory_lock,
            cycle_id=cycle_id,
            jobs=(SchedulerJobName.PORTFOLIO_SNAPSHOT,),
        )

    def _run_open_subsequence(
        self,
        *,
        scheduled_for: datetime,
        advisory_lock: AdvisoryLock,
        cycle_id: UUID | None,
        jobs: tuple[SchedulerJobName, ...],
    ) -> tuple[JobRunOutcome, ...]:
        if scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware UTC")
        already_held = advisory_lock.held
        if not advisory_lock.try_acquire():
            return (
                JobRunOutcome(
                    jobs[0],
                    scheduled_for,
                    SchedulerRunStatus.SKIPPED,
                    skipped=True,
                    error="advisory_lock_not_acquired",
                ),
            )
        try:
            return tuple(
                self.run_job(job, scheduled_for=scheduled_for, cycle_id=cycle_id)
                for job in jobs
            )
        finally:
            if not already_held:
                advisory_lock.release()

    def run_daily_open_sequence(
        self,
        *,
        scheduled_for: datetime,
        advisory_lock: AdvisoryLock,
        cycle_id: UUID | None = None,
    ) -> tuple[JobRunOutcome, ...]:
        if scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware UTC")
        gap = self.run_daily_open_gap_stop(
            scheduled_for=scheduled_for,
            advisory_lock=advisory_lock,
            cycle_id=cycle_id,
        )
        due = scheduled_for + timedelta(seconds=self._config.fill_delay_seconds)
        if self._clock.now() < due:
            return gap + (
                JobRunOutcome(
                    SchedulerJobName.NEXT_OPEN_FILL_PROCESSING,
                    scheduled_for,
                    SchedulerRunStatus.SKIPPED,
                    skipped=True,
                    error="fill_not_due",
                ),
            )
        fill = self.run_daily_open_fill(
            scheduled_for=scheduled_for,
            advisory_lock=advisory_lock,
            cycle_id=cycle_id,
        )
        snap = self.run_daily_open_snapshot(
            scheduled_for=scheduled_for,
            advisory_lock=advisory_lock,
            cycle_id=cycle_id,
        )
        return gap + fill + snap

    def run_daily_close_sequence(
        self,
        *,
        scheduled_for: datetime,
        advisory_lock: AdvisoryLock,
        cycle_id: UUID | None = None,
    ) -> tuple[JobRunOutcome, ...]:
        if scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware UTC")
        already_held = advisory_lock.held
        if not advisory_lock.try_acquire():
            return (
                JobRunOutcome(
                    SchedulerJobName.DAILY_SIGNAL_EVALUATION,
                    scheduled_for,
                    SchedulerRunStatus.SKIPPED,
                    skipped=True,
                    error="advisory_lock_not_acquired",
                ),
            )
        try:
            due = scheduled_for + timedelta(seconds=self._config.evaluation_delay_seconds)
            if self._clock.now() < due:
                return (
                    JobRunOutcome(
                        SchedulerJobName.DAILY_SIGNAL_EVALUATION,
                        scheduled_for,
                        SchedulerRunStatus.SKIPPED,
                        skipped=True,
                        error="evaluation_not_due",
                    ),
                )
            outcomes = [
                self.run_job(
                    SchedulerJobName.DAILY_SIGNAL_EVALUATION,
                    scheduled_for=scheduled_for,
                    cycle_id=cycle_id,
                ),
                self.run_job(
                    SchedulerJobName.DAILY_STOP_UPDATE,
                    scheduled_for=scheduled_for,
                    cycle_id=cycle_id,
                ),
                self.run_job(
                    SchedulerJobName.PORTFOLIO_SNAPSHOT,
                    scheduled_for=scheduled_for,
                    cycle_id=cycle_id,
                ),
            ]
            return tuple(outcomes)
        finally:
            if not already_held:
                advisory_lock.release()

    def run_job(
        self,
        job_name: str,
        *,
        scheduled_for: datetime,
        cycle_id: UUID | None = None,
    ) -> JobRunOutcome:
        if scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware UTC")
        if not self._jobs_enabled and job_name != SchedulerJobName.READINESS_CHECK:
            return JobRunOutcome(
                job_name,
                scheduled_for,
                SchedulerRunStatus.SKIPPED,
                skipped=True,
                error="scheduler_not_ready",
            )

        idem = scheduler_run_key(job_name, scheduled_for)
        existing = self._repo.get_scheduler_run(job_name, scheduled_for)
        if existing is not None:
            if existing.status == SchedulerRunStatus.COMPLETED:
                return JobRunOutcome(job_name, scheduled_for, existing.status, skipped=True)
            if existing.status == SchedulerRunStatus.RUNNING:
                return JobRunOutcome(
                    job_name,
                    scheduled_for,
                    SchedulerRunStatus.SKIPPED,
                    skipped=True,
                    error="already_running",
                )

        started = self._clock.now()
        with transaction_scope(self._repo.session):
            run, created = self._repo.insert_or_get_scheduler_run(
                SchedulerRunRow(
                    run_id=uuid4(),
                    job_name=job_name,
                    scheduled_for=scheduled_for,
                    started_at=started,
                    status=SchedulerRunStatus.RUNNING.value,
                    idempotency_key=idem,
                )
            )
            if not created and run.status == SchedulerRunStatus.COMPLETED.value:
                return JobRunOutcome(
                    job_name, scheduled_for, SchedulerRunStatus.COMPLETED, skipped=True
                )

        handler = self._handlers.get(job_name)
        if handler is None:
            self._complete_run(job_name, scheduled_for, SchedulerRunStatus.FAILED, "unknown_job")
            return JobRunOutcome(
                job_name,
                scheduled_for,
                SchedulerRunStatus.FAILED,
                skipped=False,
                error="unknown_job",
            )

        try:
            handler(scheduled_for=scheduled_for, cycle_id=cycle_id)
            self._complete_run(job_name, scheduled_for, SchedulerRunStatus.COMPLETED, None)
            return self._persisted_job_outcome(
                job_name, scheduled_for, skipped=False
            )
        except Exception as exc:
            self._complete_run(job_name, scheduled_for, SchedulerRunStatus.FAILED, str(exc))
            return self._persisted_job_outcome(
                job_name, scheduled_for, skipped=False, error=str(exc)
            )

    def _complete_run(
        self,
        job_name: str,
        scheduled_for: datetime,
        status: SchedulerRunStatus,
        error: str | None,
    ) -> SchedulerRun:
        with transaction_scope(self._repo.session):
            return self._repo.complete_scheduler_run(
                job_name=job_name,
                scheduled_for=scheduled_for,
                status=status,
                completed_at=self._clock.now(),
                error=error,
            )

    def _persisted_job_outcome(
        self,
        job_name: str,
        scheduled_for: datetime,
        *,
        skipped: bool,
        error: str | None = None,
    ) -> JobRunOutcome:
        run = self._repo.get_scheduler_run(job_name, scheduled_for)
        if run is not None:
            return JobRunOutcome(
                job_name,
                scheduled_for,
                run.status,
                skipped=skipped,
                error=run.error,
            )
        return JobRunOutcome(
            job_name,
            scheduled_for,
            SchedulerRunStatus.FAILED,
            skipped=False,
            error=error or "scheduler_run_missing",
        )

    def _job_readiness_check(self, **kwargs: Any) -> None:
        self._readiness.evaluate(
            market_data_ready=self._market_data_ready(),
            scheduler_active=self._jobs_enabled,
        )

    def _evaluation_time_for(self, scheduled_for: datetime) -> datetime:
        return scheduled_for + timedelta(seconds=self._config.evaluation_delay_seconds)

    def _job_daily_signal_evaluation(
        self, *, scheduled_for: datetime, cycle_id: UUID | None
    ) -> None:
        ctx = self._pending_evaluation or {}
        evaluation_time = self._evaluation_time_for(scheduled_for)
        for symbol in SYMBOL_PROCESSING_ORDER:
            symbol_ctx = ctx.get("symbols", {}).get(symbol)
            if symbol_ctx is None:
                continue
            self._evaluation.evaluate_symbol_for_daily_close(
                symbol=symbol,
                evaluation_time=evaluation_time,
                **symbol_ctx,
            )

    def _job_next_open_fill_processing(
        self, *, scheduled_for: datetime, cycle_id: UUID | None
    ) -> None:
        contexts = self._pending_fill_contexts or {}
        process_scheduled_intents_for_open(
            self._repo,
            self._fills,
            process_time=self._clock.now(),
            fill_delay_seconds=self._config.fill_delay_seconds,
            symbol_contexts=contexts,
            cycle_id=cycle_id,
        )

    def _job_daily_stop_update(self, *, scheduled_for: datetime, cycle_id: UUID | None) -> None:
        ctx = self._pending_stop_context or {}
        self._stops.update_daily_trailing_stops(
            evaluation_time=self._evaluation_time_for(scheduled_for),
            **ctx,
        )

    def _job_stop_trigger_processing(
        self, *, scheduled_for: datetime, cycle_id: UUID | None
    ) -> None:
        ctx = self._pending_stop_context or {}
        self._stops.process_stop_triggers_for_daily_candle(
            process_time=self._clock.now(),
            at_open=True,
            **ctx,
        )

    def _job_intraday_stop_processing(
        self, *, scheduled_for: datetime, cycle_id: UUID | None
    ) -> None:
        ctx = self._pending_stop_context or {}
        if not ctx.get("preview_candles"):
            raise ValueError("missing intraday preview_candles context")
        self._stops.process_intraday_stop_triggers(
            process_time=self._clock.now(),
            cycle_id=cycle_id,
            **ctx,
        )

    def _job_funding_processing(self, **kwargs: Any) -> None:
        raise RuntimeError("funding processing is not implemented in paper trading V1")

    def _job_portfolio_snapshot(self, *, scheduled_for: datetime, cycle_id: UUID | None) -> None:
        from paper_trading.portfolio import PortfolioSnapshotService

        PortfolioSnapshotService(self._repo).capture_snapshot(
            evaluation_time=self._evaluation_time_for(scheduled_for),
            event="scheduled_snapshot",
            cycle_id=cycle_id,
        )

    def _job_runtime_heartbeat(self, **kwargs: Any) -> None:
        self._runtime.heartbeat()
