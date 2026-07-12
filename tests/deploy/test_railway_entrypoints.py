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
