"""Persist sealed ``parameter_area.json`` (#290)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.parameter_area.evaluator import PARAMETER_AREA_FILENAME


class ParameterAreaArtifactError(Exception):
    """Overwrite or seal failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def write_parameter_area_artifact(directory: Path, artifact: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / PARAMETER_AREA_FILENAME
    if target.exists():
        raise ParameterAreaArtifactError(
            f"refusing to overwrite existing parameter area artifact: {target}"
        )
    payload = _canonical_json_bytes(artifact)
    digest = hashlib.sha256(payload).hexdigest()
    tmp = directory / f".{PARAMETER_AREA_FILENAME}.tmp"
    tmp.write_bytes(payload)
    tmp.replace(target)
    (directory / f"{PARAMETER_AREA_FILENAME}.sha256").write_text(
        f"{digest}  {PARAMETER_AREA_FILENAME}\n", encoding="utf-8"
    )
    return target


def verify_parameter_area_seal(directory: Path) -> str:
    target = directory / PARAMETER_AREA_FILENAME
    seal = directory / f"{PARAMETER_AREA_FILENAME}.sha256"
    if not target.is_file() or not seal.is_file():
        raise ParameterAreaArtifactError(
            f"missing parameter area artifact or seal under {directory}"
        )
    expected = seal.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise ParameterAreaArtifactError(
            f"parameter area seal mismatch: expected {expected}, got {actual}"
        )
    return actual
