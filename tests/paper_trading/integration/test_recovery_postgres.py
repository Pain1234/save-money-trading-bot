"""PostgreSQL integration tests for recovery."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import RuntimeStatus, SchedulerRunStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.recovery import recover_on_startup
from paper_trading.repository import PaperTradingRepository

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.conftest_execution import utc_dt


@pytest.fixture(autouse=True)
def _reset_lock() -> Iterator[None]:
    InMemoryAdvisoryLock.reset()
    yield
    InMemoryAdvisoryLock.reset()


@requires_postgres
def test_recovery_on_clean_database_reaches_ready(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("recovery-test")
    assert lock.try_acquire()
    result = recover_on_startup(
        repo,
        config,
        lock,
        market_data_ready=True,
    )
    assert result.final_status == RuntimeStatus.READY
    runtime = repo.get_runtime_state()
    assert runtime is not None
    assert runtime.status == RuntimeStatus.READY


@requires_postgres
def test_recovery_wallet_mismatch_stays_non_ready_and_emits_incident(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    repo.update_wallet(cash_delta=Decimal("1"))
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("accounting-mismatch-test")
    assert lock.try_acquire()

    result = recover_on_startup(
        repo,
        config,
        lock,
        market_data_ready=True,
    )

    assert result.final_status == RuntimeStatus.DEGRADED
    assert result.entry_readiness is False
    assert any(issue.code == "accounting_reconciliation_mismatch" for issue in result.issues)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    assert runtime.status == RuntimeStatus.DEGRADED
    assert runtime.last_error == "accounting_reconciliation_mismatch"
    incidents = [
        event
        for event in repo.list_audit_events(limit=20)
        if event.event_type == "ACCOUNTING_RECONCILIATION_INCIDENT"
    ]
    assert len(incidents) == 1
    assert "wallet cash mismatch" in incidents[0].payload_json["mismatches"][0]


@requires_postgres
def test_recovery_marks_orphan_scheduler_run_failed(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    scheduled = utc_dt(2024, 3, 1)
    from uuid import uuid4

    row = SchedulerRunRow(
        run_id=uuid4(),
        job_name="daily_signal_evaluation",
        scheduled_for=scheduled,
        started_at=scheduled,
        status=SchedulerRunStatus.RUNNING.value,
        idempotency_key="orphan-test-key",
    )
    repo.session.add(row)
    repo.session.flush()

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("orphan-test")
    lock.try_acquire()
    result = recover_on_startup(repo, config, lock, market_data_ready=True)
    assert "marked_1_orphan_scheduler_runs_failed" in result.repairs_applied
    runs = repo.get_running_scheduler_runs()
    assert runs == ()


@requires_postgres
def test_recovery_idempotent_second_run(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("recovery-idempotent")
    lock.try_acquire()
    first = recover_on_startup(repo, config, lock, market_data_ready=True)
    second = recover_on_startup(repo, config, lock, market_data_ready=True)
    assert first.final_status == RuntimeStatus.READY
    assert second.final_status in {RuntimeStatus.READY, RuntimeStatus.DEGRADED}
