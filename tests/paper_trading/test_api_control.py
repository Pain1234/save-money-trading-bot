"""API control endpoint tests."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState

from tests.paper_trading.conftest_execution import utc_dt


def _runtime_state() -> RuntimeState:
    return RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=utc_dt(2024, 1, 16),
        version=1,
    )


@pytest.fixture
def repo() -> MagicMock:
    mock = MagicMock()
    state = _runtime_state()
    mock.get_runtime_state.return_value = state
    mock.update_runtime_state.return_value = state
    mock.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    mock.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    mock.append_audit_event.return_value = MagicMock()
    return mock


@pytest.fixture
def client(repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/paper_trading_test",
    )
    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "test-secret-key")
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    return TestClient(app)


def test_control_disabled_by_default(monkeypatch: pytest.MonkeyPatch, repo: MagicMock) -> None:
    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "test-secret-key")
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    client = TestClient(app)
    response = client.post("/control/pause", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 404


def test_pause_with_valid_api_key(client: TestClient) -> None:
    response = client.post("/control/pause", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_resume_rejected_when_kill_switch(client: TestClient, repo: MagicMock) -> None:
    killed = _runtime_state().model_copy(update={"kill_switch": True})
    repo.get_runtime_state.return_value = killed
    response = client.post("/control/resume", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 409


def test_run_cycle_rejects_naive_datetime(client: TestClient) -> None:
    response = client.post(
        "/control/run-cycle",
        headers={"X-API-Key": "test-secret-key"},
        json={"job_name": "readiness_check", "scheduled_for": "2024-01-16T00:00:00"},
    )
    assert response.status_code == 400
