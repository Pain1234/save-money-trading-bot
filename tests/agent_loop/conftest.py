"""Shared fixtures for Codex review gate tests."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    candidate = here.parents[2]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=candidate,
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except OSError:
        pass
    return candidate


REPO_ROOT = _discover_repo_root()
AGENT_LOOP = REPO_ROOT / ".agent-loop"

for p in (str(REPO_ROOT), str(AGENT_LOOP)):
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
def gate_ps1(agent_loop_dir: Path) -> Path:
    return agent_loop_dir / "run-codex-review.ps1"


@pytest.fixture(scope="session")
def loop_ps1(agent_loop_dir: Path) -> Path:
    return agent_loop_dir / "run-review-loop.ps1"


def run_gate(
    *extra_args: str,
    cwd: Path | None = None,
    script: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke run-codex-review.ps1 with PowerShell (optional wrapper script)."""
    ps1 = script if script is not None else AGENT_LOOP / "run-codex-review.ps1"
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
        *extra_args,
    ]
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        env=env,
    )


@pytest.fixture
def run_gate_fn():
    return run_gate
