"""Deployment smoke tests for Railway service entrypoints."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_worker_module_imports() -> None:
    importlib.import_module("paper_trading.runner")
    importlib.import_module("paper_trading.application")


def test_readonly_api_module_imports() -> None:
    importlib.import_module("paper_trading.readonly_api")
    importlib.import_module("paper_trading.api_runner")


def test_api_runner_fails_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_TRADING_DATABASE_URL", raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "paper_trading.api_runner"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "PAPER_TRADING_DATABASE_URL" in result.stderr + result.stdout


def test_deploy_scripts_exist() -> None:
    scripts = [
        REPO_ROOT / "deploy/scripts/start-worker.sh",
        REPO_ROOT / "deploy/scripts/start-api.sh",
        REPO_ROOT / "deploy/scripts/pre-deploy-migrate.sh",
    ]
    for script in scripts:
        assert script.is_file(), script.name


def test_api_image_ships_research_local_lab_catalog() -> None:
    """Issue #270: production Lab needs examples/ in the API image."""
    dockerfile = (REPO_ROOT / "deploy/Dockerfile.paper-python").read_text(encoding="utf-8")
    assert "COPY examples ./examples" in dockerfile
    assert "RAILWAY_GIT_COMMIT_SHA" in dockerfile
    start_api = (REPO_ROOT / "deploy/scripts/start-api.sh").read_text(encoding="utf-8")
    assert "RESEARCH_DATASET_CATALOG_PATH" in start_api
    assert "examples/research/local_lab/catalog.json" in start_api
    assert "RESEARCH_GIT_COMMIT" in start_api
    catalog = REPO_ROOT / "examples/research/local_lab/catalog.json"
    assert catalog.is_file()


def test_railpack_configs_exist_and_match_service() -> None:
    import json

    configs = {
        "dashboard": ("deploy/railpack/dashboard.railpack.json", "node"),
        "worker": ("deploy/railpack/worker.railpack.json", "python"),
        "api": ("deploy/railpack/api.railpack.json", "python"),
    }
    for name, (relative_path, provider) in configs.items():
        path = REPO_ROOT / relative_path
        assert path.is_file(), name
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["provider"] == provider, name
        assert payload["deploy"]["startCommand"], name


def test_verify_paper_state_has_no_tests_import() -> None:
    source = (REPO_ROOT / "scripts/verify_paper_state.py").read_text(encoding="utf-8")
    assert "from tests" not in source
    assert "import tests" not in source


def test_verify_paper_state_imports_without_tests_package(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import importlib.util

    original_import = builtins.__import__

    def guarded_import(name: str, /, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "tests" or name.startswith("tests."):
            raise ImportError(f"blocked import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    script_path = REPO_ROOT / "scripts" / "verify_paper_state.py"
    spec = importlib.util.spec_from_file_location("verify_paper_state", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "verify")


def test_soak_helpers_use_production_state_invariants() -> None:
    from paper_trading.state_verification import assert_state_invariants

    from tests.paper_trading.soak import helpers

    assert helpers.assert_soak_invariants is assert_state_invariants
