#!/usr/bin/env python3
"""Export pinned Python dependencies for the P1 baseline lock file.

Creates a clean virtual environment, installs the project with dev extras
(non-editable, matching production ``pip install -e ".[api]"`` shape but
including test tools), and writes ``requirements-baseline.txt`` at repo root.

Preferred runtime: Python 3.12 (matches ``deploy/Dockerfile.paper-python``).
The script works on any Python >=3.11; regenerate on 3.12 before tagging when
possible.

Usage::

    python scripts/export_requirements_baseline.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "requirements-baseline.txt"
HEADER = """\
# P1 baseline Python lock (transitive pins from pip freeze).
# Regenerate: python scripts/export_requirements_baseline.py
# Preferred runtime: Python 3.12 (deploy/Dockerfile.paper-python).
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


def main() -> int:
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Using Python {py_version} ({sys.executable})")

    with tempfile.TemporaryDirectory(prefix="baseline-export-") as tmp:
        venv_dir = Path(tmp) / ".venv"
        _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=REPO_ROOT)

        if sys.platform == "win32":
            python = venv_dir / "Scripts" / "python.exe"
        else:
            python = venv_dir / "bin" / "python"

        _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=REPO_ROOT)
        _run([str(python), "-m", "pip", "install", ".[dev]"], cwd=REPO_ROOT)

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
            if line and not line.startswith("-e ")
        ]

        body = HEADER + f"# Generated with Python {py_version}\n" + "\n".join(lines) + "\n"
        OUTPUT.write_text(body, encoding="utf-8")
        print(f"Wrote {len(lines)} packages to {OUTPUT.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
