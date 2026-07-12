"""Tests for the read-only monitoring API."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperWalletState, RuntimeState
from paper_trading.readonly_api import app

from tests.paper_trading.conftest_execution import utc_dt


@pytest.fixture
def readonly_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=utc_dt(2024, 1, 16),
        version=1,
    )
    wallet = PaperWalletState(
        wallet_id=uuid4(),
        cash=Decimal("100000"),
        total_realized_pnl=Decimal("0"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        version=1,
        updated_at=utc_dt(2024, 1, 16),
    )

    repo = MagicMock()
    repo.get_runtime_state.return_value = runtime
    repo.get_wallet.return_value = wallet
    repo.get_open_positions.return_value = ()
    repo.list_positions.return_value = ()
    repo.list_orders.return_value = ()
    repo.list_fills.return_value = ()
    repo.list_stop_events.return_value = ()
    repo.list_scheduler_runs.return_value = ()
    repo.list_audit_events.return_value = ()
    repo.list_portfolio_snapshots.return_value = ()
    repo.get_running_scheduler_runs.return_value = ()
    repo.list_permanent_configuration_failures.return_value = ()

    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/paper_trading_test",
    )
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    return TestClient(app)


def test_readonly_health(readonly_client: TestClient) -> None:
    assert readonly_client.get("/health").status_code == 200


def test_readonly_rejects_post(readonly_client: TestClient) -> None:
    response = readonly_client.post("/api/v1/status")
    assert response.status_code == 405


def test_readonly_status_schema(readonly_client: TestClient) -> None:
    body = readonly_client.get("/api/v1/status").json()
    assert body["display_status"] in {"READY", "DEGRADED", "STOPPED"}
    assert "heartbeat_age_seconds" in body


def test_readonly_wallet_no_secrets(readonly_client: TestClient) -> None:
    body = readonly_client.get("/api/v1/wallet").json()
    assert "cash" in body
    assert "database_url" not in body


def test_readonly_pagination_limit(readonly_client: TestClient) -> None:
    response = readonly_client.get("/api/v1/fills?limit=200")
    assert response.status_code == 400
