"""Static checks that Issue #102 Node Playwright path stays executable."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_SPEC = REPO_ROOT / "tests" / "e2e" / "dashboard-routes.spec.ts"
PERF_CONFIG = REPO_ROOT / "playwright.perf.config.ts"
PACKAGE_JSON = REPO_ROOT / "package.json"
LOGIN_FORM = REPO_ROOT / "src" / "app" / "login" / "LoginForm.tsx"


def test_playwright_perf_files_exist() -> None:
    assert E2E_SPEC.is_file()
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


def test_login_form_has_labels_and_name_attributes() -> None:
    source = LOGIN_FORM.read_text(encoding="utf-8")
    assert "Username" in source
    assert "Password" in source
    assert 'name="username"' in source
    assert 'name="password"' in source
