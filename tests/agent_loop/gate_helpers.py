"""Import-stable helpers for Codex review gate tests (never named conftest)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


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

for p in (str(REPO_ROOT), str(AGENT_LOOP), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)


def discover_powershell() -> str:
    """Locate a PowerShell executable for gate tests (prefer pwsh)."""
    tried: list[str] = []
    pwsh = shutil.which("pwsh")
    if pwsh:
        return pwsh
    tried.append("pwsh")

    if os.name == "nt":
        powershell = shutil.which("powershell")
        if powershell:
            return powershell
        tried.append("powershell")
    else:
        tried.append("powershell (Windows only)")

    raise RuntimeError(
        "No PowerShell executable found for agent-loop gate tests. "
        f"Tried: {', '.join(tried)}. Install PowerShell 7+ (pwsh) or Windows PowerShell."
    )


def run_gate(
    *extra_args: str,
    cwd: Path | None = None,
    script: Path | None = None,
    env: dict[str, str] | None = None,
    powershell: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke run-codex-review.ps1 with discovered PowerShell (optional wrapper script)."""
    ps1 = script if script is not None else AGENT_LOOP / "run-codex-review.ps1"
    exe = powershell if powershell is not None else discover_powershell()
    args = list(extra_args)
    # Shallow CI checkouts often lack origin/main; DiffFile tests should not require it.
    has_diff_file = any(str(a).lower() == "-difffile" for a in args)
    has_base_ref = any(str(a).lower() == "-baseref" for a in args)
    if has_diff_file and not has_base_ref:
        args = ["-BaseRef", "HEAD", *args]
    cmd = [
        exe,
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
        *args,
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
