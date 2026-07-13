"""Cross-process heartbeat visibility and safe database identity tests."""

from __future__ import annotations

import logging
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
from paper_trading.db.session import create_session_factory
from paper_trading.heartbeat import persist_runtime_heartbeat
from paper_trading.readonly_api import app as readonly_app
from paper_trading.repository import PaperTradingRepository


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
