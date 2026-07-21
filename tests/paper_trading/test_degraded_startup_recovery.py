"""Regression tests for startup recovery from persisted DEGRADED runtime state."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import RuntimeStatus, SchedulerRunStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.models import RuntimeState
from paper_trading.recovery import RecoveryService, recover_on_startup
from paper_trading.transitions import InvalidTransitionError, validate_runtime_transition

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.conftest_execution import utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _runtime(status: RuntimeStatus, *, last_error: str | None = None) -> RuntimeState:
    now = utc_dt(2024, 1, 16)
    return RuntimeState(
        instance_id=uuid4(),
        status=status,
        last_error=last_error,
        heartbeat_at=now,
        version=1,
    )


def test_degraded_to_recovering_transition_allowed() -> None:
    validate_runtime_transition(RuntimeStatus.DEGRADED, RuntimeStatus.RECOVERING)


def test_degraded_to_ready_transition_still_allowed() -> None:
    validate_runtime_transition(RuntimeStatus.DEGRADED, RuntimeStatus.READY)


@pytest.mark.parametrize(
    ("target",),
    [
        (RuntimeStatus.STARTING,),
        (RuntimeStatus.SYNCING,),
        (RuntimeStatus.STOPPED,),
    ],
)
def test_degraded_invalid_transitions_rejected(target: RuntimeStatus) -> None:
    with pytest.raises(InvalidTransitionError):
        validate_runtime_transition(RuntimeStatus.DEGRADED, target)


def test_paused_and_killed_cannot_enter_recovering() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_runtime_transition(RuntimeStatus.PAUSED, RuntimeStatus.RECOVERING)
    with pytest.raises(InvalidTransitionError):
        validate_runtime_transition(RuntimeStatus.KILLED, RuntimeStatus.RECOVERING)


def _stateful_repo(
    initial: RuntimeStatus,
    *,
    last_error: str | None = None,
) -> MagicMock:
    state = _runtime(initial, last_error=last_error)
    repo = MagicMock()
    repo.get_running_scheduler_runs.return_value = ()
    repo.list_all_intents.return_value = ()
    repo.list_all_positions.return_value = ()
    repo.list_all_fills.return_value = ()
    repo.list_positions.return_value = ()
    repo.get_open_positions.return_value = ()
    repo.get_wallet.return_value = MagicMock(
        cash=Decimal("100000"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        total_realized_pnl=Decimal("0"),
    )
    repo.count_open_positions_by_symbol.return_value = {}
    repo.session.execute.return_value = None
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    repo.append_audit_event.return_value = MagicMock()

    def get_runtime_state() -> RuntimeState:
        return state

    def update_runtime_state(**kwargs: object) -> RuntimeState:
        nonlocal state
        updates: dict[str, object] = {}
        if kwargs.get("status") is not None:
            updates["status"] = kwargs["status"]
        if "last_error" in kwargs:
            updates["last_error"] = kwargs["last_error"]
        if kwargs.get("heartbeat_at") is not None:
            updates["heartbeat_at"] = kwargs["heartbeat_at"]
        if kwargs.get("expected_version") is not None:
            updates["version"] = int(kwargs["expected_version"]) + 1
        state = state.model_copy(update=updates)
        return state

    repo.get_runtime_state.side_effect = get_runtime_state
    repo.update_runtime_state.side_effect = update_runtime_state
    return repo


def test_recover_from_degraded_ready_path_runs_migration_and_checks() -> None:
    repo = _stateful_repo(
        RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
    )

    lock = InMemoryAdvisoryLock("unit-degraded-ready")
    lock.try_acquire()
    service = RecoveryService(repo, _config(), clock=MagicMock(now=lambda: utc_dt(2024, 1, 16)))
    with patch.object(service, "_migration_at_head", return_value=True) as migration:
        with patch.object(service, "run_consistency_checks", return_value=[]) as checks:
            with patch.object(service, "apply_auto_repairs", return_value=[]) as repairs:
                with patch.object(service, "_capture_recovery_snapshot") as snapshot:
                    result = service.recover_on_startup(lock, market_data_ready=True)

    migration.assert_called_once()
    assert checks.call_count == 2
    repairs.assert_called_once()
    snapshot.assert_called_once()
    assert result.final_status == RuntimeStatus.READY
    statuses = [
        c.kwargs.get("status")
        for c in repo.update_runtime_state.call_args_list
        if c.kwargs.get("status") is not None
    ]
    assert statuses[0] == RuntimeStatus.RECOVERING
    assert RuntimeStatus.SYNCING in statuses
    assert statuses[-1] == RuntimeStatus.READY


def test_recover_from_degraded_stays_degraded_when_market_data_not_ready() -> None:
    repo = _stateful_repo(
        RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
    )

    lock = InMemoryAdvisoryLock("unit-degraded-not-ready")
    lock.try_acquire()
    service = RecoveryService(repo, _config(), clock=MagicMock(now=lambda: utc_dt(2024, 1, 16)))
    with patch.object(service, "_migration_at_head", return_value=True):
        with patch.object(service, "run_consistency_checks", return_value=[]):
            with patch.object(service, "apply_auto_repairs", return_value=[]):
                result = service.recover_on_startup(lock, market_data_ready=False)

    assert result.final_status == RuntimeStatus.DEGRADED
    degraded_calls = [
        c for c in repo.update_runtime_state.call_args_list
        if c.kwargs.get("status") == RuntimeStatus.DEGRADED
    ]
    assert degraded_calls
    assert degraded_calls[-1].kwargs.get("last_error") == "market_data_not_ready"


def test_recover_from_paused_fails_closed() -> None:
    repo = MagicMock()
    repo.get_runtime_state.return_value = _runtime(RuntimeStatus.PAUSED)
    repo.session.execute.return_value = None
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)

    lock = InMemoryAdvisoryLock("unit-paused")
    lock.try_acquire()
    service = RecoveryService(repo, _config(), clock=MagicMock(now=lambda: utc_dt(2024, 1, 16)))
    with pytest.raises(InvalidTransitionError):
        service.recover_on_startup(lock, market_data_ready=True)


@requires_postgres
@pytest.mark.postgres
def test_persisted_degraded_recovers_to_ready_when_market_data_ready(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    repo.session.flush()

    config = _config()
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("pg-degraded-ready")
    assert lock.try_acquire()
    result = recover_on_startup(repo, config, lock, market_data_ready=True)

    assert result.final_status == RuntimeStatus.READY
    runtime = repo.get_runtime_state()
    assert runtime is not None
    assert runtime.status == RuntimeStatus.READY
    assert not runtime.last_error


@requires_postgres
@pytest.mark.postgres
def test_persisted_degraded_stays_degraded_when_market_data_not_ready(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    repo.session.flush()

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("pg-degraded-not-ready")
    assert lock.try_acquire()
    result = recover_on_startup(repo, config, lock, market_data_ready=False)

    assert result.final_status == RuntimeStatus.DEGRADED
    runtime = repo.get_runtime_state()
    assert runtime is not None
    assert runtime.status == RuntimeStatus.DEGRADED
    assert runtime.last_error == "market_data_not_ready"


@requires_postgres
@pytest.mark.postgres
def test_persisted_degraded_recovery_runs_consistency_repairs(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    scheduled = utc_dt(2024, 3, 1)
    repo.session.add(
        SchedulerRunRow(
            run_id=uuid4(),
            job_name="daily_signal_evaluation",
            scheduled_for=scheduled,
            started_at=scheduled,
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key="degraded-orphan-key",
        )
    )
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    repo.session.flush()

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("pg-degraded-orphan")
    assert lock.try_acquire()
    result = recover_on_startup(repo, config, lock, market_data_ready=True)

    assert result.final_status == RuntimeStatus.READY
    assert "marked_1_orphan_scheduler_runs_failed" in result.repairs_applied
    assert repo.get_running_scheduler_runs() == ()


@requires_postgres
@pytest.mark.postgres
def test_persisted_paused_does_not_auto_recover(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.PAUSED,
        expected_version=runtime.version,
    )
    repo.session.flush()

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("pg-paused")
    assert lock.try_acquire()
    with pytest.raises(InvalidTransitionError):
        recover_on_startup(repo, config, lock, market_data_ready=True)


@requires_postgres
@pytest.mark.postgres
def test_persisted_killed_does_not_auto_recover(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.KILLED,
        expected_version=runtime.version,
    )
    repo.session.flush()

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("pg-killed")
    assert lock.try_acquire()
    with pytest.raises(InvalidTransitionError):
        recover_on_startup(repo, config, lock, market_data_ready=True)


@requires_postgres
@pytest.mark.postgres
def test_railway_restart_from_degraded_is_idempotent(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    repo.session.flush()

    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("pg-degraded-idempotent")
    assert lock.try_acquire()

    first = recover_on_startup(repo, config, lock, market_data_ready=True)
    counts_after_first = (
        len(repo.list_all_fills()),
        len(repo.list_all_intents()),
        len(repo.list_all_orders()),
        len(repo.list_scheduler_runs(limit=10_000)),
    )
    second = recover_on_startup(repo, config, lock, market_data_ready=True)
    counts_after_second = (
        len(repo.list_all_fills()),
        len(repo.list_all_intents()),
        len(repo.list_all_orders()),
        len(repo.list_scheduler_runs(limit=10_000)),
    )

    assert first.final_status == RuntimeStatus.READY
    assert second.final_status == RuntimeStatus.READY
    assert counts_after_first == counts_after_second
