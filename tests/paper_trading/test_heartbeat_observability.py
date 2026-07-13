"""Cross-process heartbeat visibility and safe database identity tests."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from paper_trading import api_dependencies
from paper_trading.clock import FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.database_identity import (
    DatabaseIdentity,
    database_fingerprint,
    inspect_database_identity,
    log_database_identity,
)
from paper_trading.db.session import create_db_engine, create_session_factory
from paper_trading.heartbeat import (
    HeartbeatRetryExhausted,
    persist_runtime_heartbeat,
    persist_runtime_heartbeat_with_retry,
)
from paper_trading.readonly_api import app as readonly_app
from paper_trading.repository import PaperTradingRepository
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.paper_trading.conftest import _postgres_url


def test_worker_and_readonly_api_use_same_database_fingerprint() -> None:
    worker_url = "postgresql://worker:worker-secret@db.internal:5432/paper"
    api_url = "postgresql://readonly:api-secret@DB.INTERNAL:5432/paper"

    assert database_fingerprint(worker_url) == database_fingerprint(api_url)


def test_different_databases_have_different_fingerprints() -> None:
    first = database_fingerprint("postgresql://user:secret@db.internal:5432/paper_a")
    second = database_fingerprint("postgresql://user:secret@db.internal:5432/paper_b")

    assert first != second


def test_database_identity_log_contains_no_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("database-identity-test")
    identity = DatabaseIdentity(
        service_role="worker",
        database_fingerprint=database_fingerprint(
            "postgresql://secret-user:secret-password@secret-host:6543/paper_prod"
        ),
        current_database="paper_prod",
        environment_name="production",
        alembic_revision="009",
    )

    with caplog.at_level(logging.INFO, logger=logger.name):
        log_database_identity(logger, identity)

    rendered = caplog.text
    assert identity.database_fingerprint in rendered
    assert "paper_prod" in rendered
    for secret in (
        "secret-user",
        "secret-password",
        "secret-host",
        "6543",
        "postgresql://",
    ):
        assert secret not in rendered


@pytest.mark.postgres
def test_worker_and_api_inspect_same_connected_database(migrated_engine) -> None:
    worker = inspect_database_identity(migrated_engine, service_role="worker")
    api = inspect_database_identity(migrated_engine, service_role="readonly-api")

    assert worker.database_fingerprint == api.database_fingerprint
    assert worker.current_database == api.current_database == "paper_trading_test"
    assert worker.alembic_revision == api.alembic_revision
    assert worker.alembic_revision is not None


@pytest.mark.postgres
def test_committed_worker_heartbeat_is_visible_in_existing_second_session(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    clock = FixedClock(datetime(2026, 7, 13, 12, 0, tzinfo=UTC))

    with factory() as api_session:
        api_repo = PaperTradingRepository(api_session)
        before = api_repo.get_runtime_state()
        assert before is not None

        result = persist_runtime_heartbeat(factory, clock=clock)
        observed_by_api = api_repo.get_runtime_state()

    assert result.observed.heartbeat_at == clock.now()
    assert result.observed.version == result.previous.version + 1
    assert observed_by_api is not None
    assert observed_by_api.heartbeat_at == clock.now()
    assert observed_by_api.version == result.observed.version


@pytest.mark.postgres
def test_heartbeat_persists_while_market_data_is_degraded(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    clock = FixedClock(datetime(2026, 7, 13, 12, 5, tzinfo=UTC))

    result = persist_runtime_heartbeat(factory, clock=clock)

    assert result.observed.heartbeat_at == clock.now()
    assert result.observed.status == result.previous.status


@pytest.mark.postgres
def test_readonly_api_refreshes_runtime_from_postgres_without_session_cache(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    config = PaperTradingConfig(database_url=str(migrated_engine.url))
    clock = FixedClock(datetime(2026, 7, 13, 12, 10, tzinfo=UTC))

    with factory() as api_session:
        api_repo = PaperTradingRepository(api_session)
        readonly_app.dependency_overrides[api_dependencies.get_repository] = lambda: api_repo
        readonly_app.dependency_overrides[api_dependencies.get_config] = lambda: config
        client = TestClient(readonly_app)
        try:
            before = client.get("/api/v1/status").json()["runtime"]
            committed = persist_runtime_heartbeat(factory, clock=clock)
            after = client.get("/api/v1/status").json()["runtime"]
        finally:
            readonly_app.dependency_overrides.clear()

    assert before["heartbeat_at"] != after["heartbeat_at"]
    observed_at = datetime.fromisoformat(after["heartbeat_at"].replace("Z", "+00:00"))
    assert observed_at == clock.now()
    assert after["version"] == committed.observed.version


class _TrackingSession(Session):
    created: list[_TrackingSession] = []
    started = threading.Event()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.rollback_calls = 0
        self.close_calls = 0
        self.created.append(self)
        self.started.set()

    def rollback(self) -> None:
        self.rollback_calls += 1
        super().rollback()

    def close(self) -> None:
        self.close_calls += 1
        super().close()


@pytest.mark.postgres
def test_heartbeat_success_closes_write_and_verification_sessions(migrated_engine) -> None:
    _TrackingSession.created = []
    _TrackingSession.started.clear()
    factory = sessionmaker(
        bind=migrated_engine,
        class_=_TrackingSession,
        autoflush=False,
        expire_on_commit=False,
    )

    persist_runtime_heartbeat(
        factory,
        clock=FixedClock(datetime(2026, 7, 13, 12, 20, tzinfo=UTC)),
    )

    assert len(_TrackingSession.created) == 2
    assert all(session.close_calls == 1 for session in _TrackingSession.created)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_blocked_heartbeat_rolls_back_closes_and_retries_after_release(
    migrated_engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _TrackingSession.created = []
    _TrackingSession.started.clear()
    heartbeat_engine = create_db_engine(
        _postgres_url(),
        application_name="paper-worker-heartbeat",
    )
    blocker_engine = create_db_engine(
        _postgres_url(),
        application_name="paper-worker-scheduler",
    )
    factory = sessionmaker(
        bind=heartbeat_engine,
        class_=_TrackingSession,
        autoflush=False,
        expire_on_commit=False,
    )
    blocker = blocker_engine.connect()
    observer = migrated_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    blocker_transaction = blocker.begin()
    blocker.execute(
        text(
            "UPDATE runtime_state SET heartbeat_at = heartbeat_at "
            "WHERE instance_id = '00000000-0000-0000-0000-000000000001'"
        )
    )
    clock = FixedClock(datetime(2026, 7, 13, 12, 25, tzinfo=UTC))
    logging.getLogger("paper_trading.heartbeat").disabled = False
    caplog.set_level(logging.WARNING, logger="paper_trading.heartbeat")
    try:
        task = asyncio.create_task(
            persist_runtime_heartbeat_with_retry(
                factory,
                clock=clock,
                max_attempts=3,
                base_delay_seconds=0.05,
                lock_timeout_seconds=0.2,
                diagnostic_delay_seconds=0.01,
                jitter=lambda _low, _high: 0.0,
            )
        )
        assert await asyncio.to_thread(_TrackingSession.started.wait, 1.0)
        heartbeat_is_blocked = False
        for _ in range(100):
            heartbeat_is_blocked = bool(
                observer.execute(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_stat_activity "
                        "WHERE application_name = 'paper-worker-heartbeat' "
                        "AND cardinality(pg_blocking_pids(pid)) > 0)"
                    )
                ).scalar_one()
            )
            if heartbeat_is_blocked:
                break
            await asyncio.sleep(0.01)
        assert heartbeat_is_blocked
        await asyncio.sleep(0.25)
        blocker_transaction.commit()
        result = await task
    finally:
        if blocker_transaction.is_active:
            blocker_transaction.rollback()
        blocker.close()
        observer.close()
        blocker_engine.dispose()
        heartbeat_engine.dispose()

    assert result.observed.heartbeat_at == clock.now()
    assert result.attempts >= 2
    failed_attempts = _TrackingSession.created[:-2]
    assert failed_attempts
    assert all(session.rollback_calls >= 1 for session in failed_attempts)
    assert all(session.close_calls == 1 for session in _TrackingSession.created)
    rendered = caplog.text
    assert "runtime_heartbeat_lock_timeout" in rendered
    assert "blocked_relation=runtime_state" in rendered
    assert "blocking_application_name=paper-worker-scheduler" in rendered
    for secret in ("postgresql://", "password", "instance_id"):
        assert secret not in rendered.lower()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_final_lock_timeout_exhaustion_closes_every_attempt(migrated_engine) -> None:
    _TrackingSession.created = []
    _TrackingSession.started.clear()
    heartbeat_engine = create_db_engine(
        _postgres_url(),
        application_name="paper-worker-heartbeat",
    )
    factory = sessionmaker(
        bind=heartbeat_engine,
        class_=_TrackingSession,
        autoflush=False,
        expire_on_commit=False,
    )
    blocker = migrated_engine.connect()
    blocker_transaction = blocker.begin()
    blocker.execute(
        text(
            "UPDATE runtime_state SET heartbeat_at = heartbeat_at "
            "WHERE instance_id = '00000000-0000-0000-0000-000000000001'"
        )
    )
    try:
        with pytest.raises(HeartbeatRetryExhausted):
            await persist_runtime_heartbeat_with_retry(
                factory,
                clock=FixedClock(datetime(2026, 7, 13, 12, 30, tzinfo=UTC)),
                max_attempts=2,
                base_delay_seconds=0.01,
                lock_timeout_seconds=0.05,
                jitter=lambda _low, _high: 0.0,
            )
    finally:
        blocker_transaction.rollback()
        blocker.close()
        heartbeat_engine.dispose()

    assert len(_TrackingSession.created) == 2
    assert all(session.rollback_calls >= 1 for session in _TrackingSession.created)
    assert all(session.close_calls == 1 for session in _TrackingSession.created)
