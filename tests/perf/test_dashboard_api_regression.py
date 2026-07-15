"""Reporting-only dashboard API latency checks (P2.5 / Issue #102).

These tests are marked ``reporting`` and are **excluded from the default CI unit
job** (``not reporting``). Run manually or in a release gate:

    pytest tests/perf -m reporting -q
    PAPER_RAILWAY_API_BASE_URL=... pytest tests/perf -m reporting -q
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperWalletState, RuntimeState
from paper_trading.readonly_api import app

from tests.postgres_fixtures import _postgres_url, requires_postgres

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "docs" / "operations"
BASELINE_FIXTURE = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "perf" / "baseline-sample.json").read_text(
        encoding="utf-8"
    )
)
BUDGETS = BASELINE_FIXTURE["p25_budgets_ms"]
MEASURED = BASELINE_FIXTURE.get("measured_local_warm_p95_ms", {})
LOCAL_REGRESSION_FACTOR = 3.0

CORE_PATHS: tuple[tuple[str, str], ...] = (
    ("status", "/api/v1/status"),
    ("wallet", "/api/v1/wallet"),
    ("positions", "/api/v1/positions?limit=50"),
    ("orders", "/api/v1/orders?limit=50"),
    ("fills", "/api/v1/fills?limit=50"),
    ("equity", "/api/v1/equity?limit=100"),
    ("dashboard_summary", "/api/v1/dashboard-summary"),
)


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
    repo.list_positions.return_value = ()
    repo.list_orders.return_value = ()
    repo.list_fills.return_value = ()
    repo.list_portfolio_snapshots.return_value = ()
    repo.list_permanent_configuration_failures.return_value = ()
    repo.get_running_scheduler_runs.return_value = ()

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
    """Reporting-only: relaxed guardrail (not a CI merge gate)."""
    p95 = _warm_p95_ms(perf_client, "/api/v1/status")
    budget = BUDGETS["status_p95"]
    assert p95 < budget * 10, (
        f"status warm p95 {p95:.1f}ms exceeds relaxed budget {budget * 10}ms"
    )


@pytest.mark.reporting
def test_core_endpoints_return_200(perf_client: TestClient) -> None:
    for _name, path in CORE_PATHS:
        assert perf_client.get(path).status_code == 200, path


@pytest.mark.reporting
def test_dashboard_summary_schema_and_headers(perf_client: TestClient) -> None:
    response = perf_client.get("/api/v1/dashboard-summary")
    assert response.status_code == 200
    body = response.json()
    assert "wallet" in body
    assert response.headers.get("X-Correlation-Id")
    # Cache-Control is Issue #99; assert only when present.
    cache = response.headers.get("Cache-Control", "")
    if cache:
        assert "max-age=" in cache


@pytest.mark.reporting
def test_readonly_api_rejects_mutations(perf_client: TestClient) -> None:
    assert perf_client.post("/api/v1/dashboard-summary").status_code == 405


@pytest.fixture
def postgres_perf_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Real PostgreSQL via get_db_session — no repository mock."""
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", _postgres_url())
    app.dependency_overrides.clear()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _measured_regression_ceiling_ms(endpoint: str, *, fallback_budget_key: str) -> float:
    measured = MEASURED.get(endpoint)
    if measured is not None:
        return float(measured) * LOCAL_REGRESSION_FACTOR
    return BUDGETS[fallback_budget_key] * 10


def _write_reporting_artifact(payload: dict[str, object]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / "dashboard-perf-regression-report.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


@requires_postgres
@pytest.mark.postgres
@pytest.mark.reporting
def test_postgres_core_endpoints_warm_p95_artifact(
    postgres_perf_client: TestClient,
) -> None:
    """Real PostgreSQL: measure core routes and write CI/release artifact."""
    results: dict[str, float] = {}
    for name, path in CORE_PATHS:
        results[name] = _warm_p95_ms(postgres_perf_client, path, runs=5)
    artifact = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "mode": "reporting",
        "database": "paper_trading_test",
        "warm_p95_ms": results,
        "caveat": "warm_runs=5 → p95 ≈ max; prefer scripts/measure with --warm-runs 20",
    }
    path = _write_reporting_artifact(artifact)
    assert path.is_file()
    status_ceiling = _measured_regression_ceiling_ms(
        "status",
        fallback_budget_key="status_p95",
    )
    assert results["status"] < status_ceiling
    assert results["dashboard_summary"] < BUDGETS["overview_warm_p95"]


@requires_postgres
@pytest.mark.postgres
@pytest.mark.reporting
def test_postgres_status_returns_correlation_header(
    postgres_perf_client: TestClient,
) -> None:
    response = postgres_perf_client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-Id")


@pytest.mark.reporting
def test_railway_dashboard_summary_when_configured() -> None:
    """Optional Railway measurement — set PAPER_RAILWAY_API_BASE_URL."""
    base_url = os.environ.get("PAPER_RAILWAY_API_BASE_URL")
    if not base_url:
        pytest.skip("PAPER_RAILWAY_API_BASE_URL not set")
    url = f"{base_url.rstrip('/')}/api/v1/dashboard-summary"
    started = time.perf_counter()
    request = Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urlopen(request, timeout=30) as resp:
        body = resp.read()
        status = resp.status
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert status == 200, body[:200]
    assert elapsed_ms < BUDGETS["overview_warm_p95"], (
        f"Railway dashboard-summary {elapsed_ms:.1f}ms exceeds overview budget "
        f"{BUDGETS['overview_warm_p95']}ms"
    )


@pytest.mark.reporting
def test_playwright_dashboard_routes_when_configured() -> None:
    """Optional Playwright path — set PAPER_DASHBOARD_BASE_URL + credentials.

    Covers login → overview, positions, fills, equity when env is present.
    """
    base = os.environ.get("PAPER_DASHBOARD_BASE_URL")
    user = os.environ.get("PAPER_DASHBOARD_USER")
    password = os.environ.get("PAPER_DASHBOARD_PASSWORD")
    if not base or not user or not password:
        pytest.skip(
            "Playwright path requires PAPER_DASHBOARD_BASE_URL, "
            "PAPER_DASHBOARD_USER, PAPER_DASHBOARD_PASSWORD"
        )
    playwright = pytest.importorskip("playwright.sync_api")
    routes = ("/dashboard", "/dashboard/positions", "/dashboard/fills", "/dashboard/equity")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{base.rstrip('/')}/login")
        page.fill('input[name="username"]', user)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard**", timeout=15000)
        for route in routes:
            page.goto(f"{base.rstrip('/')}{route}")
            page.wait_for_load_state("networkidle")
            assert page.locator("body").count() == 1
        browser.close()
