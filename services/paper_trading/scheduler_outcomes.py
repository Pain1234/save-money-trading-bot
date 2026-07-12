"""Classification helpers for scheduler job run outcomes."""

from __future__ import annotations

from paper_trading.enums import SchedulerRunStatus
from paper_trading.market_event_errors import RetryableSchedulerDeferred
from paper_trading.scheduler import JobRunOutcome

RETRYABLE_SKIP_ERRORS = frozenset(
    {
        "advisory_lock_not_acquired",
        "scheduler_not_ready",
        "already_running",
        "fill_not_due",
        "evaluation_not_due",
    }
)


def is_idempotent_completed(outcome: JobRunOutcome) -> bool:
    """Job already persisted as COMPLETED — safe idempotent success."""
    return (
        outcome.status == SchedulerRunStatus.COMPLETED
        and outcome.skipped
        and outcome.error is None
    )


def is_fresh_completed(outcome: JobRunOutcome) -> bool:
    return outcome.status == SchedulerRunStatus.COMPLETED and not outcome.skipped


def is_retryable_skip(outcome: JobRunOutcome) -> bool:
    return outcome.skipped and outcome.error in RETRYABLE_SKIP_ERRORS


def is_terminal_job_success(outcome: JobRunOutcome) -> bool:
    return is_idempotent_completed(outcome) or is_fresh_completed(outcome)


def require_successful_jobs(outcomes: tuple[JobRunOutcome, ...]) -> None:
    """Raise when any inner job failed or returned a retryable skip."""
    for outcome in outcomes:
        if outcome.status == SchedulerRunStatus.FAILED:
            raise RuntimeError(outcome.error or "scheduler job failed")
        if is_retryable_skip(outcome):
            raise RetryableSchedulerDeferred(outcome.error or "scheduler_deferred")
