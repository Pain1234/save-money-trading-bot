"""#408: baseline lock must cover declared runtime deps for --no-deps installs."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "requirements-baseline.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# PEP 508 requirement name before extras / version markers.
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _requirement_name(spec: str) -> str:
    match = _REQ_NAME.match(spec)
    assert match is not None, f"unparseable requirement: {spec!r}"
    return match.group(1).lower().replace("_", "-")


def _baseline_package_names() -> set[str]:
    names: set[str] = set()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "==" not in stripped:
            continue
        names.add(stripped.split("==", 1)[0].lower().replace("_", "-"))
    return names


def test_baseline_includes_project_and_api_runtime_dependencies() -> None:
    """Dockerfile installs baseline then ``.[api] --no-deps`` (#377 / #408).

    Declared runtime packages must therefore appear in the freeze, or the API
    crashes on import (Railway healthcheck) — as with missing ``jsonschema``.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    required = [_requirement_name(s) for s in data["project"]["dependencies"]]
    required.extend(
        _requirement_name(s) for s in data["project"]["optional-dependencies"]["api"]
    )
    # ``psycopg[binary]`` freezes as psycopg + psycopg-binary.
    aliases = {
        "psycopg": {"psycopg", "psycopg-binary"},
    }
    baseline = _baseline_package_names()
    missing: list[str] = []
    for name in required:
        if name in aliases:
            if not aliases[name] <= baseline:
                missing.append(name)
        elif name not in baseline:
            missing.append(name)
    assert not missing, (
        "requirements-baseline.txt missing declared runtime deps "
        f"{missing}; regenerate with: py -3.12 scripts/export_requirements_baseline.py"
    )


def test_baseline_pins_jsonschema_for_research_import_chain() -> None:
    """Explicit pin for the #408 failure mode (research.validation → jsonschema)."""
    text = BASELINE.read_text(encoding="utf-8")
    assert re.search(r"^jsonschema==\d", text, flags=re.MULTILINE)
