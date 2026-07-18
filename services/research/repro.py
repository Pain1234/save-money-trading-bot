"""CI double-run semantic artifact comparison (Issue #146 / P4-06)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.identity import semantic_artifact_hash

# Intentional non-determinism: must not participate in semantic compares.
_NON_SEMANTIC_MANIFEST_KEYS: frozenset[str] = frozenset(
    {"attempt_id", "created_at_utc"}
)

SEMANTIC_ARTIFACT_NAMES: tuple[str, ...] = (
    "metrics.json",
    "trades.json",
    "equity.json",
    "costs.json",
    "experiment.json",
    "chart_data.json",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_manifest_from_file(path: Path) -> dict[str, Any]:
    """Load run_manifest.json excluding attempt_id / created_at_utc."""
    raw = _load_json(path)
    if not isinstance(raw, dict):
        msg = "run_manifest.json must be an object"
        raise ValueError(msg)
    return {k: v for k, v in raw.items() if k not in _NON_SEMANTIC_MANIFEST_KEYS}


def hash_semantic_artifact(path: Path) -> str:
    """Hash one artifact file for double-run compares."""
    name = path.name
    if name == "run_manifest.json":
        return semantic_artifact_hash(semantic_manifest_from_file(path))
    if name.endswith(".json"):
        payload = _load_json(path)
        return semantic_artifact_hash(payload)
    return semantic_artifact_hash(path.read_bytes())


def compare_semantic_run_dirs(a: Path, b: Path) -> dict[str, str]:
    """Assert two complete run dirs match on semantic hashes.

    Returns the shared semantic hash map (artifact name → digest).
    Raises ValueError on divergence.
    """
    hashes_a: dict[str, str] = {}
    hashes_b: dict[str, str] = {}
    names = (*SEMANTIC_ARTIFACT_NAMES, "run_manifest.json")
    for name in names:
        path_a = a / name
        path_b = b / name
        if not path_a.is_file():
            msg = f"missing artifact in first run: {name}"
            raise FileNotFoundError(msg)
        if not path_b.is_file():
            msg = f"missing artifact in second run: {name}"
            raise FileNotFoundError(msg)
        hashes_a[name] = hash_semantic_artifact(path_a)
        hashes_b[name] = hash_semantic_artifact(path_b)
        if hashes_a[name] != hashes_b[name]:
            msg = (
                f"semantic hash mismatch for {name}: "
                f"{hashes_a[name]} != {hashes_b[name]}"
            )
            raise ValueError(msg)
    return hashes_a
