"""Scheduler advisory lock contention tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import SchedulerRunStatus
from paper_trading.ids import scheduler_run_key
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.repository import PaperTradingRepository
from sqlalchemy import create_engine

from tests.paper_trading.conftest import _postgres_url, requires_postgres

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_second_scheduler_process_blocked_by_advisory_lock() -> None:
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    engine = create_engine(_postgres_url())
    lock_a = PostgresAdvisoryLock(engine, config.advisory_lock_id)
    lock_b = PostgresAdvisoryLock(engine, config.advisory_lock_id)
    try:
        assert lock_a.try_acquire() is True
        assert lock_b.try_acquire() is False
    finally:
        lock_a.release()
        engine.dispose()


def test_scheduler_run_deduplicated(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    scheduled = datetime(2024, 4, 1, tzinfo=UTC)
    key = scheduler_run_key("readiness_check", scheduled)
    row = SchedulerRunRow(
        run_id=uuid4(),
        job_name="readiness_check",
        scheduled_for=scheduled,
        status=SchedulerRunStatus.COMPLETED.value,
        idempotency_key=key,
    )
    _, created1 = repo.insert_or_get_scheduler_run(row)
    _, created2 = repo.insert_or_get_scheduler_run(row)
    assert created1 is True
    assert created2 is False


def test_naive_scheduled_for_rejected_by_scheduler(db_session) -> None:
    from paper_trading.config import PaperTradingConfig
    from paper_trading.evaluation import PaperEvaluationService
    from paper_trading.execution import PaperFillService
    from paper_trading.lock import InMemoryAdvisoryLock
    from paper_trading.scheduler import PaperTradingScheduler
    from paper_trading.stops import StopLifecycleService

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    repo = PaperTradingRepository(db_session)
    scheduler = PaperTradingScheduler(
        repo,
        config,
        evaluation_service=PaperEvaluationService(repo),
        fill_service=PaperFillService(repo),
        stop_service=StopLifecycleService(repo, config=config),
    )
    lock = InMemoryAdvisoryLock("sched-test")
    lock.try_acquire()
    with pytest.raises(ValueError, match="timezone-aware"):
        scheduler.run_daily_open_sequence(
            scheduled_for=datetime(2024, 1, 1),
            advisory_lock=lock,
        )
