"""Reporting-only dashboard API latency regression checks (P2.5 / Issue #102)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperWalletState, RuntimeState
from paper_trading.readonly_api import app

REPO_ROOT = Path(__file__).resolve().parents[2]
BUDGETS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "perf" / "baseline-sample.json").read_text(
        encoding="utf-8"
    )
)["p25_budgets_ms"]


@pytest.fixture
def perf_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
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
    repo.list_permanent_configuration_failures.return_value = ()

    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/paper_trading_test",
    )
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: repo
    return TestClient(app)


def _warm_p95_ms(client: TestClient, path: str, *, runs: int = 5) -> float:
    timings: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        response = client.get(path)
        assert response.status_code == 200
        timings.append((time.perf_counter() - started) * 1000.0)
    timings.sort()
    index = max(0, min(len(timings) - 1, int(round(0.95 * (len(timings) - 1)))))
    return timings[index]


@pytest.mark.reporting
def test_status_endpoint_warm_p95_within_local_budget(perf_client: TestClient) -> None:
    """Reporting-only: relaxed guardrail against gross regressions in CI."""
    p95 = _warm_p95_ms(perf_client, "/api/v1/status")
    budget = BUDGETS["status_p95"]
    assert p95 < budget * 10, f"status warm p95 {p95:.1f}ms exceeds relaxed budget {budget * 10}ms"


@pytest.mark.reporting
def test_dashboard_summary_schema_and_headers(perf_client: TestClient) -> None:
    response = perf_client.get("/api/v1/dashboard-summary")
    assert response.status_code == 200
    body = response.json()
    assert "wallet" in body
    assert response.headers.get("X-Correlation-Id")
    assert "max-age=2" in response.headers.get("Cache-Control", "")


@pytest.mark.reporting
def test_readonly_api_rejects_mutations(perf_client: TestClient) -> None:
    assert perf_client.post("/api/v1/dashboard-summary").status_code == 405
