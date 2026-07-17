"""Pytest fixtures for Codex review gate tests (fixtures only — no helpers)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
from gate_helpers import AGENT_LOOP, REPO_ROOT

# Ensure agent_loop and .agent-loop are importable.
for p in (str(REPO_ROOT), str(AGENT_LOOP), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def agent_loop_dir(repo_root: Path) -> Path:
    return repo_root / ".agent-loop"


@pytest.fixture(scope="session")
def schema_path(agent_loop_dir: Path) -> Path:
    return agent_loop_dir / "codex-review-schema.json"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def validate_mod(agent_loop_dir: Path):
    return _load_module(
        "validate_review_result_gate",
        agent_loop_dir / "validate-review-result.py",
    )


@pytest.fixture(scope="session")
def secret_scan_mod(agent_loop_dir: Path):
    return _load_module("secret_scan_gate", agent_loop_dir / "secret_scan.py")


@pytest.fixture(scope="session")
def build_workspace_mod(agent_loop_dir: Path):
    return _load_module(
        "build_review_workspace_gate",
        agent_loop_dir / "build_review_workspace.py",
    )


@pytest.fixture(scope="session")
def gate_ps1(agent_loop_dir: Path) -> Path:
    return agent_loop_dir / "run-codex-review.ps1"


@pytest.fixture(scope="session")
def loop_ps1(agent_loop_dir: Path) -> Path:
    return agent_loop_dir / "run-review-loop.ps1"


@pytest.fixture
def run_gate_fn():
    from gate_helpers import run_gate

    return run_gate
