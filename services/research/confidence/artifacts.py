"""Persist sealed ``confidence_profile.json`` (#288)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.confidence.evaluator import CONFIDENCE_PROFILE_FILENAME


class ConfidenceArtifactError(Exception):
    """Overwrite or seal failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def write_confidence_profile_artifact(
    directory: Path, artifact: dict[str, Any]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / CONFIDENCE_PROFILE_FILENAME
    if target.exists():
        raise ConfidenceArtifactError(
            f"refusing to overwrite existing confidence profile: {target}"
        )
    payload = _canonical_json_bytes(artifact)
    digest = hashlib.sha256(payload).hexdigest()
    tmp = directory / f".{CONFIDENCE_PROFILE_FILENAME}.tmp"
    tmp.write_bytes(payload)
    tmp.replace(target)
    (directory / f"{CONFIDENCE_PROFILE_FILENAME}.sha256").write_text(
        f"{digest}  {CONFIDENCE_PROFILE_FILENAME}\n", encoding="utf-8"
    )
    return target


def verify_confidence_profile_seal(directory: Path) -> str:
    target = directory / CONFIDENCE_PROFILE_FILENAME
    seal = directory / f"{CONFIDENCE_PROFILE_FILENAME}.sha256"
    if not target.is_file() or not seal.is_file():
        raise ConfidenceArtifactError(
            f"missing confidence profile artifact or seal under {directory}"
        )
    expected = seal.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise ConfidenceArtifactError(
            f"confidence profile seal mismatch: expected {expected}, got {actual}"
        )
    return actual
