"""Persist ``regime_metrics.json`` (#287)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.regime_quality.evaluator import REGIME_METRICS_FILENAME


class RegimeMetricsArtifactError(Exception):
    """Overwrite or seal failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def write_regime_metrics_artifact(
    directory: Path, artifact: dict[str, Any]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / REGIME_METRICS_FILENAME
    if target.exists():
        raise RegimeMetricsArtifactError(
            f"refusing to overwrite existing regime metrics: {target}"
        )
    payload = _canonical_json_bytes(artifact)
    digest = hashlib.sha256(payload).hexdigest()
    tmp = directory / f".{REGIME_METRICS_FILENAME}.tmp"
    tmp.write_bytes(payload)
    tmp.replace(target)
    (directory / f"{REGIME_METRICS_FILENAME}.sha256").write_text(
        f"{digest}  {REGIME_METRICS_FILENAME}\n", encoding="utf-8"
    )
    return target


def verify_regime_metrics_seal(directory: Path) -> str:
    target = directory / REGIME_METRICS_FILENAME
    seal = directory / f"{REGIME_METRICS_FILENAME}.sha256"
    if not target.is_file() or not seal.is_file():
        raise RegimeMetricsArtifactError(
            f"missing regime metrics artifact or seal under {directory}"
        )
    expected = seal.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise RegimeMetricsArtifactError(
            f"regime metrics seal mismatch: expected {expected}, got {actual}"
        )
    return actual
