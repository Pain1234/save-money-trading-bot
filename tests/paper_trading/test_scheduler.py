"""Tests for paper trading scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from paper_trading.clock import FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import SchedulerRunStatus
from paper_trading.evaluation import PaperEvaluationService
from paper_trading.execution import PaperFillService
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.scheduler import PaperTradingScheduler, SchedulerJobName
from paper_trading.stops import StopLifecycleService

from tests.paper_trading.conftest_execution import utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _scheduler(clock_time) -> PaperTradingScheduler:
    repo = MagicMock()
    repo.get_scheduler_run.return_value = None
    repo.insert_or_get_scheduler_run.return_value = (
        MagicMock(status=SchedulerRunStatus.RUNNING.value),
        True,
    )
    repo.complete_scheduler_run.return_value = MagicMock()
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    return PaperTradingScheduler(
        repo,
        _config(),
        evaluation_service=MagicMock(spec=PaperEvaluationService),
        fill_service=MagicMock(spec=PaperFillService),
        stop_service=MagicMock(spec=StopLifecycleService),
        clock=FixedClock(clock_time),
    )


def test_scheduler_run_twice_second_skipped() -> None:
    scheduled = utc_dt(2024, 1, 16)
    repo = MagicMock()
    completed = MagicMock(status=SchedulerRunStatus.COMPLETED.value)
    repo.get_scheduler_run.return_value = completed
    repo.insert_or_get_scheduler_run.return_value = (completed, False)
    scheduler = PaperTradingScheduler(
        repo,
        _config(),
        evaluation_service=MagicMock(),
        fill_service=MagicMock(),
        stop_service=MagicMock(),
        clock=FixedClock(scheduled),
    )
    outcome = scheduler.run_job(SchedulerJobName.RUNTIME_HEARTBEAT, scheduled_for=scheduled)
    assert outcome.skipped is True


def test_naive_scheduled_for_rejected() -> None:
    scheduler = _scheduler(utc_dt(2024, 1, 16))
    with pytest.raises(ValueError, match="timezone-aware"):
        scheduler.run_job(
            SchedulerJobName.RUNTIME_HEARTBEAT,
            scheduled_for=__import__("datetime").datetime(2024, 1, 16),
        )


def test_daily_close_before_delay_skipped() -> None:

    scheduled = utc_dt(2024, 1, 15, 23, 59, 59)
    scheduler = _scheduler(scheduled)
    lock = InMemoryAdvisoryLock("test-daily-close")
    InMemoryAdvisoryLock.reset()
    outcomes = scheduler.run_daily_close_sequence(
        scheduled_for=scheduled,
        advisory_lock=lock,
    )
    assert outcomes[0].skipped is True
    assert outcomes[0].error == "evaluation_not_due"
    InMemoryAdvisoryLock.reset()


def test_second_process_cannot_acquire_lock() -> None:
    InMemoryAdvisoryLock.reset()
    lock_a = InMemoryAdvisoryLock("primary")
    lock_b = InMemoryAdvisoryLock("secondary")
    assert lock_a.try_acquire() is True
    assert lock_b.try_acquire() is False
    lock_a.release()
    InMemoryAdvisoryLock.reset()
