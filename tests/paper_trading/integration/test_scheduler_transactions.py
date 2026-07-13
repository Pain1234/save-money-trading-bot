"""PostgreSQL regression tests for scheduler/API transaction commits."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from paper_trading.clock import FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import SchedulerRunStatus
from paper_trading.evaluation import PaperEvaluationService
from paper_trading.execution import PaperFillService
from paper_trading.runtime import RuntimeService
from paper_trading.scheduler import PaperTradingScheduler, SchedulerJobName
from paper_trading.stops import StopLifecycleService
from sqlalchemy.orm import Session, sessionmaker

from tests.paper_trading.conftest import requires_postgres

pytestmark = [requires_postgres, pytest.mark.postgres]


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env()


def _scheduler(session: Session, clock_time: datetime) -> PaperTradingScheduler:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(session)
    return PaperTradingScheduler(
        repo,
        _config(),
        evaluation_service=PaperEvaluationService(repo, clock=FixedClock(clock_time)),
        fill_service=PaperFillService(repo),
        stop_service=StopLifecycleService(repo, config=_config()),
        clock=FixedClock(clock_time),
        runtime=RuntimeService(repo, clock=FixedClock(clock_time)),
        market_data_ready=lambda: True,
    )


def test_scheduler_run_completed_persists_after_new_session(
    postgres_commit_session: Session,
    migrated_engine,
) -> None:
    scheduled = datetime(2024, 1, 16, 0, 0, 5, tzinfo=UTC)
    scheduler = _scheduler(postgres_commit_session, scheduled)
    scheduler.set_jobs_enabled(True)
    outcome = scheduler.run_job(SchedulerJobName.RUNTIME_HEARTBEAT, scheduled_for=scheduled)
    assert outcome.status == SchedulerRunStatus.COMPLETED
    postgres_commit_session.commit()

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository

        run = PaperTradingRepository(fresh).get_scheduler_run(
            SchedulerJobName.RUNTIME_HEARTBEAT, scheduled
        )
        assert run is not None
        assert run.status == SchedulerRunStatus.COMPLETED


def test_scheduler_run_failed_persists_on_exception(
    postgres_commit_session: Session, migrated_engine
) -> None:
    scheduled = datetime(2024, 1, 16, 0, 1, 0, tzinfo=UTC)
    scheduler = _scheduler(postgres_commit_session, scheduled)
    scheduler.set_jobs_enabled(True)
    scheduler._handlers[SchedulerJobName.RUNTIME_HEARTBEAT] = (  # noqa: SLF001
        lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    outcome = scheduler.run_job(SchedulerJobName.RUNTIME_HEARTBEAT, scheduled_for=scheduled)
    assert outcome.status == SchedulerRunStatus.FAILED
    assert postgres_commit_session.in_transaction() is False

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        from paper_trading.repository import PaperTradingRepository

        run = PaperTradingRepository(fresh).get_scheduler_run(
            SchedulerJobName.RUNTIME_HEARTBEAT, scheduled
        )
        assert run is not None
        assert run.status == SchedulerRunStatus.FAILED


def test_heartbeat_visible_in_new_session(
    postgres_commit_session: Session, migrated_engine
) -> None:
    scheduled = datetime(2024, 1, 16, 0, 2, 0, tzinfo=UTC)
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(postgres_commit_session)
    runtime = RuntimeService(repo, clock=FixedClock(scheduled))
    before = runtime.get_state().heartbeat_at
    runtime.heartbeat()
    after = runtime.get_state().heartbeat_at
    assert after >= before
    postgres_commit_session.commit()

    factory = sessionmaker(bind=migrated_engine)
    with factory() as fresh:
        persisted = PaperTradingRepository(fresh).get_runtime_state()
        assert persisted is not None
        assert persisted.heartbeat_at == after
