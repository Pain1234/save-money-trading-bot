"""API security tests."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState

from tests.paper_trading.conftest_execution import utc_dt


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/paper_trading_test",
    )
    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "correct-key")
    repo = MagicMock()
    repo.get_runtime_state.return_value = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=utc_dt(2024, 1, 16),
        version=1,
    )
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    repo.append_audit_event.return_value = MagicMock()
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    return TestClient(app)


def test_missing_api_key_rejected(client: TestClient) -> None:
    response = client.post("/control/pause")
    assert response.status_code == 403


def test_wrong_api_key_rejected(client: TestClient) -> None:
    response = client.post("/control/pause", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 403


def test_error_response_has_no_secrets(client: TestClient) -> None:
    response = client.post("/control/pause", headers={"X-API-Key": "wrong-key"})
    assert "correct-key" not in response.text
    assert "PAPER_CONTROL" not in response.text
