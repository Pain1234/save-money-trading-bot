"""Static checks that Issue #250 Research Playwright smoke stays executable."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_SPEC = REPO_ROOT / "tests" / "visual" / "research-routes.spec.ts"
PLAYWRIGHT_CONFIG = REPO_ROOT / "playwright.config.ts"
PAPER_API_STUB = REPO_ROOT / "scripts" / "paper-api-stub.mjs"
PACKAGE_JSON = REPO_ROOT / "package.json"
CI_FAST = REPO_ROOT / ".github" / "workflows" / "ci-fast.yml"


def test_research_playwright_smoke_files_exist() -> None:
    assert RESEARCH_SPEC.is_file()
    assert PLAYWRIGHT_CONFIG.is_file()
    assert PAPER_API_STUB.is_file()
    package = PACKAGE_JSON.read_text(encoding="utf-8")
    assert "@playwright/test" in package
    assert "test:research-smoke" in package


def test_research_stub_is_read_only_for_research_routes() -> None:
    source = PAPER_API_STUB.read_text(encoding="utf-8")
    assert 'url.startsWith("/api/v1/research/")' in source
    assert 'method !== "GET" && method !== "HEAD"' in source
    assert "405" in source


def test_research_smoke_spec_covers_workspace_switch_and_routes() -> None:
    source = RESEARCH_SPEC.read_text(encoding="utf-8")
    for route in (
        "/dashboard/research",
        "/dashboard/research/strategies",
        "/dashboard/research/experiments/new",
        "/dashboard/research/compare",
        "/dashboard/research/robustness",
        "/dashboard/research/validation",
    ):
        assert route in source
    assert 'getByTestId("workspace-monitor")' in source
    assert "405" in source


def test_ci_fast_wires_research_playwright_smoke_job() -> None:
    workflow = CI_FAST.read_text(encoding="utf-8")
    assert "research-playwright-smoke:" in workflow
    assert "npm run test:research-smoke" in workflow
