"""Static checks that Issue #102 Node Playwright path stays executable."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_SPEC = REPO_ROOT / "tests" / "e2e" / "dashboard-routes.spec.ts"
LAYER_A_SPEC = REPO_ROOT / "tests" / "e2e" / "dashboard-layer-a-perf.spec.ts"
PERF_CONFIG = REPO_ROOT / "playwright.perf.config.ts"
PACKAGE_JSON = REPO_ROOT / "package.json"
LOGIN_FORM = REPO_ROOT / "src" / "app" / "login" / "LoginForm.tsx"
SKELETON = REPO_ROOT / "src" / "components" / "monitor" / "PageSkeleton.tsx"


def test_playwright_perf_files_exist() -> None:
    assert E2E_SPEC.is_file()
    assert LAYER_A_SPEC.is_file()
    assert PERF_CONFIG.is_file()
    package = PACKAGE_JSON.read_text(encoding="utf-8")
    assert "@playwright/test" in package
    assert "test:dashboard-perf" in package


def test_playwright_spec_uses_stable_label_selectors() -> None:
    source = E2E_SPEC.read_text(encoding="utf-8")
    assert 'getByLabel("Username")' in source
    assert 'getByLabel("Password")' in source
    assert "/dashboard/positions" in source
    assert "/dashboard/fills" in source
    assert "/dashboard/equity" in source


def test_layer_a_spec_covers_required_routes_and_skeleton() -> None:
    source = LAYER_A_SPEC.read_text(encoding="utf-8")
    for route in (
        "/dashboard",
        "/dashboard/status",
        "/dashboard/positions",
        "/dashboard/orders",
        "/dashboard/fills",
        "/dashboard/equity",
        "/dashboard/incidents",
    ):
        assert route in source
    assert 'data-testid="dashboard-skeleton"' in source
    assert "PerformanceObserver" in source
    assert "browser.newContext()" in source
    assert "Promise.race" in source
    assert "await skeletonWatch" not in source
    skeleton = SKELETON.read_text(encoding="utf-8")
    assert 'data-testid="dashboard-skeleton"' in skeleton


def test_login_form_has_labels_and_name_attributes() -> None:
    source = LOGIN_FORM.read_text(encoding="utf-8")
    assert "Username" in source
    assert "Password" in source
    assert 'name="username"' in source
    assert 'name="password"' in source
