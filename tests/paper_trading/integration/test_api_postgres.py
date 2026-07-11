"""PostgreSQL integration tests for API read endpoints."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app, set_market_data_ready, set_scheduler_active
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.recovery import recover_on_startup
from paper_trading.repository import PaperTradingRepository

from tests.paper_trading.conftest import _postgres_url, requires_postgres


@pytest.fixture(autouse=True)
def _reset_lock() -> Iterator[None]:
    InMemoryAdvisoryLock.reset()
    yield
    InMemoryAdvisoryLock.reset()


@pytest.fixture
def api_client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", _postgres_url())
    repo = PaperTradingRepository(db_session)
    config = PaperTradingConfig.from_env(database_url=_postgres_url())
    lock = InMemoryAdvisoryLock("api-pg-test")
    lock.try_acquire()
    recover_on_startup(repo, config, lock, market_data_ready=True)
    runtime = repo.get_runtime_state()
    if runtime and runtime.status != RuntimeStatus.READY:
        repo.update_runtime_state(status=RuntimeStatus.READY, expected_version=runtime.version)

    set_market_data_ready(True)
    set_scheduler_active(True)

    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


@requires_postgres
def test_api_runtime_against_postgres(api_client: TestClient) -> None:
    response = api_client.get("/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == RuntimeStatus.READY.value
    assert body["heartbeat_at"].endswith("Z")


@requires_postgres
def test_api_health_against_postgres(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
