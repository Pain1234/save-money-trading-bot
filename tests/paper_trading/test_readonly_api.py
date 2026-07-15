"""Tests for the read-only monitoring API."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperWalletState, RuntimeState
from paper_trading.readonly_api import app


@pytest.fixture
def readonly_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    now = datetime.now(UTC)
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
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
        updated_at=now,
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
    client = TestClient(app)
    client._repo = repo  # type: ignore[attr-defined]
    return client


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


def test_readonly_ready_worker_reports_full_readiness(readonly_client: TestClient) -> None:
    body = readonly_client.get("/api/v1/status").json()
    readiness = body["readiness"]
    assert body["display_status"] == "READY"
    assert readiness["market_data_ready"] is True
    assert readiness["runtime_readiness"] is True
    assert readiness["entry_readiness"] is True
    assert readiness["last_error"] is None
def test_readonly_dashboard_summary_schema(readonly_client: TestClient) -> None:
    body = readonly_client.get("/api/v1/dashboard-summary").json()
    assert body["display_status"] in {"READY", "DEGRADED", "STOPPED"}
    assert "wallet" in body
    assert "open_position_count" in body
    assert "position_summary" in body
    assert "warnings" in body
    assert body["status"]["display_status"] == body["display_status"]


def test_readonly_perf_and_cache_headers(readonly_client: TestClient) -> None:
    response = readonly_client.get("/api/v1/status")
    assert response.headers.get("X-Correlation-Id")
    assert "max-age=2" in response.headers.get("Cache-Control", "")


def test_status_uses_single_runtime_snapshot(readonly_client: TestClient) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    repo.get_runtime_state.reset_mock()
    readonly_client.get("/api/v1/status")
    assert repo.get_runtime_state.call_count == 1


def test_runtime_last_error_is_sanitized_in_status(readonly_client: TestClient) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        last_error="invalid api_key secret",
        version=1,
    )
    repo.get_runtime_state.return_value = runtime
    body = readonly_client.get("/api/v1/status").json()
    assert body["runtime"]["last_error"] == "sanitized error"


def test_market_data_skips_full_readiness_evaluate(readonly_client: TestClient) -> None:
    with patch("paper_trading.readonly_api.ReadinessService") as readiness_cls:
        readonly_client.get("/api/v1/market-data")
        readiness_cls.assert_not_called()
