# Dashboard performance and security bundle checks
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_PATH = REPO_ROOT / "src/lib/paper-api/client.ts"
DASHBOARD_ROOT = REPO_ROOT / "src/app/dashboard"
COMPONENTS_DASHBOARD = REPO_ROOT / "src/components/dashboard"
MIDDLEWARE_PATH = REPO_ROOT / "src/middleware.ts"

LOADING_ROUTES = (
    "loading.tsx",
    "status/loading.tsx",
    "positions/loading.tsx",
    "wallet/loading.tsx",
    "orders/loading.tsx",
    "fills/loading.tsx",
    "stops/loading.tsx",
    "scheduler/loading.tsx",
    "equity/loading.tsx",
    "incidents/loading.tsx",
)

FORBIDDEN_MOCK_IMPORTS = (
    "mock-data",
    "@/lib/mock-data",
    "financial-fixtures",
    "@/lib/demo/financial-fixtures",
)


def _client_source() -> str:
    return CLIENT_PATH.read_text(encoding="utf-8")


def test_dashboard_client_uses_server_side_env_only() -> None:
    source = _client_source()
    assert "process.env.PRIVATE_PAPER_API_URL" in source
    assert "NEXT_PUBLIC_" not in source


def test_dashboard_client_cache_policy() -> None:
    source = _client_source()
    assert "REVALIDATE" in source
    # Object keys and/or usages (mergeable across stacked PR bases).
    assert "STATUS:" in source or "REVALIDATE.STATUS" in source
    assert "SUMMARY:" in source or "REVALIDATE.SUMMARY" in source
    assert "fetchDashboardSummary" in source
    assert "next: { revalidate:" in source
    assert "revalidate: REVALIDATE.SUMMARY" in source


def test_dashboard_overview_uses_summary_fetch() -> None:
    """Core overview must use summary only — no fan-out Promise.all on the page."""
    source = (DASHBOARD_ROOT / "page.tsx").read_text(encoding="utf-8")
    assert "fetchDashboardSummary" in source
    assert "Promise.all" not in source
    assert "Promise.allSettled" not in source
    assert "Suspense" in source
    assert "fetchEquity" not in source
    assert "fetchOpenPositions" not in source
    assert "fetchFills" not in source


def test_dashboard_client_has_open_positions_helper() -> None:
    source = _client_source()
    assert "fetchOpenPositions" in source
    assert "open_only" in source


def test_dashboard_client_has_api_timeout() -> None:
    source = _client_source()
    assert "AbortController" in source
    assert "API_TIMEOUT_MS = 5000" in source
    assert "PaperApiTimeoutError" in source
    assert "getMonitoringErrorMessage" in source


def test_dashboard_status_parallelizes_fetches() -> None:
    source = (DASHBOARD_ROOT / "status/page.tsx").read_text(encoding="utf-8")
    assert "Promise.all" in source


def test_dashboard_loading_states_exist() -> None:
    for relative_path in LOADING_ROUTES:
        path = DASHBOARD_ROOT / relative_path
        assert path.is_file(), relative_path
        source = path.read_text(encoding="utf-8")
        assert "PageSkeleton" in source or "Skeleton" in source


def test_dashboard_pages_do_not_use_mock_data() -> None:
    for page in DASHBOARD_ROOT.rglob("page.tsx"):
        source = page.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_MOCK_IMPORTS:
            assert forbidden not in source, f"{page}: {forbidden}"


def test_dashboard_components_do_not_use_financial_mocks() -> None:
    """Production design components must not pull demo financial fixtures."""
    for path in COMPONENTS_DASHBOARD.rglob("*.tsx"):
        source = path.read_text(encoding="utf-8")
        assert "financial-fixtures" not in source, path
        assert "@/lib/demo/" not in source, path
        # Live tables/charts/controls must not import legacy mock-data
        if path.name in {
            "DashboardMain.tsx",
            "Tables.tsx",
            "PerformanceChart.tsx",
            "PerformanceChartSection.tsx",
            "MarketCards.tsx",
            "ControlPanels.tsx",
        }:
            assert "mock-data" not in source, path


def test_dashboard_pages_use_monitoring_error_helper() -> None:
    for page in DASHBOARD_ROOT.rglob("page.tsx"):
        source = page.read_text(encoding="utf-8")
        if "fetch" in source or "PaperApi" in source:
            assert "getMonitoringErrorMessage" in source


def test_dashboard_auth_middleware_protects_routes() -> None:
    source = MIDDLEWARE_PATH.read_text(encoding="utf-8")
    assert 'matcher: ["/dashboard/:path*"]' in source
    assert "session.isLoggedIn" in source


def test_dashboard_controls_are_disabled_in_source() -> None:
    controls = (COMPONENTS_DASHBOARD / "ControlPanels.tsx").read_text(encoding="utf-8")
    assert 'data-testid="bot-start-button"' in controls
    assert "disabled" in controls
    assert "nicht verfügbar" in controls.lower() or "nicht verfügbar" in controls


def test_dashboard_build_succeeds() -> None:
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **__import__("os").environ,
            "SESSION_SECRET": "x" * 32,
            "PRIVATE_PAPER_API_URL": "http://127.0.0.1:8080",
            "AUTH_USERNAME": "monitor",
            "AUTH_PASSWORD_HASH": "$2a$12$testhashfortestbuildonlyxxxxxxxxxxxxxxxxxxxxxx",
        },
    )
    assert result.returncode == 0, result.stderr[-4000:] + result.stdout[-4000:]


def test_built_client_bundle_does_not_expose_private_api_url() -> None:
    static_dir = REPO_ROOT / ".next" / "static"
    if not static_dir.exists():
        return
    leaked = False
    pattern = re.compile(
        r"paper-trading-api\.railway\.internal|PRIVATE_PAPER_API_URL|127\.0\.0\.1:8080"
    )
    for path in static_dir.rglob("*.js"):
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            leaked = True
            break
    assert not leaked
