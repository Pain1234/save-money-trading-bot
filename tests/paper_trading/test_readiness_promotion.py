"""Tests for DEGRADED -> READY promotion readiness."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from paper_trading.application import FakeMarketDataRuntime, PaperTradingApplication
from paper_trading.clock import FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.models import RuntimeState
from paper_trading.readiness import ReadinessService

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.conftest_execution import utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _runtime(
    status: RuntimeStatus,
    *,
    last_error: str | None = None,
    heartbeat_at=None,
) -> RuntimeState:
    now = utc_dt(2024, 1, 16)
    return RuntimeState(
        instance_id=uuid4(),
        status=status,
        last_error=last_error,
        heartbeat_at=heartbeat_at or now,
        version=1,
    )


def _repo(runtime: RuntimeState) -> MagicMock:
    repo = MagicMock()
    repo.get_runtime_state.return_value = runtime
    repo.get_running_scheduler_runs.return_value = ()
    repo.list_permanent_configuration_failures.return_value = ()
    return repo


def test_promotion_from_degraded_with_market_data_ready() -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=now)
    repo = _repo(runtime)
    lock = InMemoryAdvisoryLock("promotion-ready")
    lock.try_acquire()
    service = ReadinessService(repo, _config(), clock=FixedClock(now))
    try:
        snap = service.evaluate_ready_promotion(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=True,
        )
        assert snap.ready is True
        assert snap.reasons == ()
    finally:
        lock.release()
        InMemoryAdvisoryLock.reset()


def test_promotion_blocked_when_market_data_not_ready() -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=now)
    service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(now))
    snap = service.evaluate_ready_promotion(market_data_ready=False, scheduler_active=True)
    assert snap.ready is False
    assert "market_data_not_ready" in snap.reasons


def test_promotion_blocked_without_advisory_lock() -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=now)
    lock = InMemoryAdvisoryLock("promotion-no-lock")
    service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(now))
    snap = service.evaluate_ready_promotion(
        market_data_ready=True,
        advisory_lock=lock,
        scheduler_active=True,
    )
    assert snap.ready is False
    assert "advisory_lock_not_held" in snap.reasons


def test_promotion_blocked_when_scheduler_not_active() -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=now)
    lock = InMemoryAdvisoryLock("promotion-no-scheduler")
    lock.try_acquire()
    service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(now))
    try:
        snap = service.evaluate_ready_promotion(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=False,
        )
        assert snap.ready is False
        assert "scheduler_not_active" in snap.reasons
    finally:
        lock.release()
        InMemoryAdvisoryLock.reset()


def test_promotion_blocked_when_migration_not_at_head() -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=now)
    lock = InMemoryAdvisoryLock("promotion-migration")
    lock.try_acquire()
    db_engine = MagicMock()
    db_engine.connect.return_value.__enter__ = MagicMock(
        return_value=MagicMock(
            execute=MagicMock(return_value=MagicMock(scalar_one_or_none=lambda: "old_rev"))
        )
    )
    db_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    alembic_config = MagicMock()
    service = ReadinessService(
        _repo(runtime),
        _config(),
        clock=FixedClock(now),
        db_engine=db_engine,
        alembic_config=alembic_config,
    )
    with patch(
        "paper_trading.readiness.ScriptDirectory.from_config",
        return_value=MagicMock(get_current_head=lambda: "head_rev"),
    ):
        try:
            snap = service.evaluate_ready_promotion(
                market_data_ready=True,
                advisory_lock=lock,
                scheduler_active=True,
            )
        finally:
            lock.release()
            InMemoryAdvisoryLock.reset()
    assert snap.ready is False
    assert "migration_not_at_head" in snap.reasons


@pytest.mark.parametrize(
    ("status",),
    [
        (RuntimeStatus.PAUSED,),
        (RuntimeStatus.KILLED,),
        (RuntimeStatus.READY,),
    ],
)
def test_promotion_not_allowed_for_non_promotable_status(status: RuntimeStatus) -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(status, heartbeat_at=now)
    lock = InMemoryAdvisoryLock(f"promotion-{status.value}")
    lock.try_acquire()
    service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(now))
    try:
        snap = service.evaluate_ready_promotion(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=True,
        )
        assert snap.ready is False
        assert "runtime_not_promotable" in snap.reasons
    finally:
        lock.release()
        InMemoryAdvisoryLock.reset()


def test_evaluate_still_requires_ready_status() -> None:
    now = utc_dt(2024, 1, 16)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=now)
    lock = InMemoryAdvisoryLock("evaluate-strict")
    lock.try_acquire()
    service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(now))
    try:
        snap = service.evaluate(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=True,
        )
        assert snap.runtime_readiness is False
        assert "runtime_not_ready" in snap.reasons
        assert "last_error_set" in snap.reasons
    finally:
        lock.release()
        InMemoryAdvisoryLock.reset()


def test_stale_heartbeat_blocks_promotion_until_refreshed() -> None:
    old = utc_dt(2024, 1, 16)
    fresh = old + timedelta(seconds=400)
    runtime = _runtime(RuntimeStatus.DEGRADED, last_error="market_data_not_ready", heartbeat_at=old)
    lock = InMemoryAdvisoryLock("promotion-stale-heartbeat")
    lock.try_acquire()
    service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(fresh))
    try:
        stale = service.evaluate_ready_promotion(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=True,
        )
        assert stale.ready is False
        assert "stale_heartbeat" in stale.reasons

        runtime = runtime.model_copy(update={"heartbeat_at": fresh})
        service = ReadinessService(_repo(runtime), _config(), clock=FixedClock(fresh))
        fresh_snap = service.evaluate_ready_promotion(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=True,
        )
        assert fresh_snap.ready is True
    finally:
        lock.release()
        InMemoryAdvisoryLock.reset()


@requires_postgres
@pytest.mark.postgres
@pytest.mark.asyncio
async def test_application_promotes_degraded_after_market_data_ready(
    migrated_engine,
    alembic_config,
    postgres_commit_session,
) -> None:
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    repo = PaperTradingRepository(postgres_commit_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    postgres_commit_session.commit()

    config = PaperServiceConfig.from_env(database_url=_postgres_url())
    app = PaperTradingApplication(
        config=config,
        market_data_runtime=FakeMarketDataRuntime(),
        alembic_config=alembic_config,
    )
    await app.start()
    try:
        runtime = app.repository.get_runtime_state()
        assert runtime is not None
        assert runtime.status == RuntimeStatus.READY
        assert not runtime.last_error
    finally:
        await app.stop()


@requires_postgres
@pytest.mark.postgres
@pytest.mark.asyncio
async def test_application_restart_promotion_is_idempotent(
    migrated_engine,
    alembic_config,
    postgres_commit_session,
) -> None:
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    repo = PaperTradingRepository(postgres_commit_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    postgres_commit_session.commit()

    config = PaperServiceConfig.from_env(database_url=_postgres_url())

    async def _start_and_counts() -> tuple[int, int, int, int]:
        app = PaperTradingApplication(
            config=config,
            market_data_runtime=FakeMarketDataRuntime(),
            alembic_config=alembic_config,
        )
        await app.start()
        counts = (
            len(app.repository.list_all_fills()),
            len(app.repository.list_all_intents()),
            len(app.repository.list_all_orders()),
            len(app.repository.list_scheduler_runs(limit=10_000)),
        )
        await app.stop()
        return counts

    first_counts = await _start_and_counts()
    second_counts = await _start_and_counts()
    assert first_counts == second_counts


@requires_postgres
@pytest.mark.postgres
@pytest.mark.asyncio
async def test_degraded_to_ready_readonly_api_integration(
    migrated_engine,
    alembic_config,
    postgres_commit_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient
    from paper_trading.application import PaperTradingApplication
    from paper_trading.readonly_api import app as readonly_app
    from paper_trading.repository import PaperTradingRepository
    from paper_trading.service_config import PaperServiceConfig

    repo = PaperTradingRepository(postgres_commit_session)
    runtime = repo.get_runtime_state()
    assert runtime is not None
    repo.update_runtime_state(
        status=RuntimeStatus.DEGRADED,
        last_error="market_data_not_ready",
        expected_version=runtime.version,
    )
    postgres_commit_session.commit()

    config = PaperServiceConfig.from_env(database_url=_postgres_url())
    worker = PaperTradingApplication(
        config=config,
        market_data_runtime=FakeMarketDataRuntime(),
        alembic_config=alembic_config,
    )
    await worker.start()
    try:
        runtime = worker.repository.get_runtime_state()
        assert runtime is not None
        assert runtime.status == RuntimeStatus.READY

        from paper_trading import api_dependencies

        readonly_app.dependency_overrides[api_dependencies.get_repository] = (
            lambda: worker.repository
        )
        readonly_app.dependency_overrides[api_dependencies.get_config] = lambda: config
        client = TestClient(readonly_app)
        body = client.get("/api/v1/status").json()
        readiness = body["readiness"]
        assert body["display_status"] == "READY"
        assert readiness["market_data_ready"] is True
        assert readiness["runtime_readiness"] is True
        assert readiness["entry_readiness"] is True
        assert readiness["last_error"] is None
    finally:
        readonly_app.dependency_overrides.clear()
        await worker.stop()
