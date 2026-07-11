"""API read endpoint tests."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app, set_market_data_ready, set_scheduler_active
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState

from tests.paper_trading.conftest_execution import utc_dt


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=utc_dt(2024, 1, 16),
        version=1,
    )

    repo = MagicMock()
    repo.get_runtime_state.return_value = runtime
    repo.get_wallet.return_value = None
    repo.get_latest_portfolio_snapshot.return_value = None
    repo.get_open_positions.return_value = ()
    repo.list_positions.return_value = ()
    repo.list_intents.return_value = ()
    repo.list_orders.return_value = ()
    repo.list_fills.return_value = ()
    repo.list_evaluations.return_value = ()
    repo.list_audit_events.return_value = ()
    repo.list_scheduler_runs.return_value = ()
    repo.get_running_scheduler_runs.return_value = ()

    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/paper_trading_test",
    )
    set_market_data_ready(True)
    set_scheduler_active(True)

    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    return TestClient(app)


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_structured_body(client: TestClient) -> None:
    response = client.get("/readiness")
    assert response.status_code in {200, 503}
    body = response.json()
    assert "process_liveness" in body
    assert "entry_readiness" in body


def test_runtime_decimal_and_uuid_format(client: TestClient) -> None:
    response = client.get("/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["heartbeat_at"].endswith("Z")
    assert isinstance(body["instance_id"], str)
