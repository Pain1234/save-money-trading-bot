#!/usr/bin/env python3
"""Export pinned Python dependencies for the P1 baseline lock file.

Creates a clean virtual environment, installs the project with dev extras
(editable, matching local dev ``pip install -e ".[dev]"``), and writes
``requirements-baseline.txt`` at repo root containing **PyPI pins only** —
local project references (``-e``, ``file://``, absolute paths) are stripped.

**Regeneration requires Python 3.12** (matches ``deploy/Dockerfile.paper-python``).
CI and baseline lock files must be produced on 3.12; the script warns on other
versions.

Usage::

    py -3.12 scripts/export_requirements_baseline.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "requirements-baseline.txt"
HEADER = """\
# P1 baseline Python lock (transitive PyPI pins from pip freeze).
# Regenerate (Python 3.12 required): py -3.12 scripts/export_requirements_baseline.py
# Matches deploy/Dockerfile.paper-python (Python 3.12).
# Install from repo root: pip install -r requirements-baseline.txt
# Then install this package: pip install -e ".[dev]"  OR  pip install .
"""


def _run(cmd: list[str], *, cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr}\n{result.stdout}"
        )


def _is_local_project_ref(line: str) -> bool:
    """Return True if *line* is an editable or path install of this repo."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("-e "):
        return True
    lower = stripped.lower()
    if "file://" in lower:
        return True
    repo_posix = REPO_ROOT.as_posix().lower()
    repo_win = str(REPO_ROOT).lower().replace("\\", "/")
    normalized = stripped.lower().replace("\\", "/")
    if repo_posix in normalized or repo_win in normalized:
        return True
    # pip freeze may emit: save-money-bot @ file:///...
    if stripped.startswith("save-money-bot") and "@" in stripped:
        return True
    return False


def main() -> int:
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Using Python {py_version} ({sys.executable})")
    if sys.version_info[:2] != (3, 12):
        print(
            "WARNING: regenerate on Python 3.12 to match deploy/Dockerfile.paper-python.",
            file=sys.stderr,
        )

    with tempfile.TemporaryDirectory(prefix="baseline-export-") as tmp:
        venv_dir = Path(tmp) / ".venv"
        _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=REPO_ROOT)

        if sys.platform == "win32":
            python = venv_dir / "Scripts" / "python.exe"
        else:
            python = venv_dir / "bin" / "python"

        _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=REPO_ROOT)
        _run([str(python), "-m", "pip", "install", "-e", ".[dev]"], cwd=REPO_ROOT)

        freeze = subprocess.run(
            [str(python), "-m", "pip", "freeze"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        lines = [
            line
            for line in freeze.stdout.splitlines()
            if line and not _is_local_project_ref(line)
        ]

        body = HEADER + f"# Generated with Python {py_version}\n" + "\n".join(lines) + "\n"
        OUTPUT.write_text(body, encoding="utf-8")
        print(f"Wrote {len(lines)} packages to {OUTPUT.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
