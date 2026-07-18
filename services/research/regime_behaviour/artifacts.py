"""Persist ``behavior_profile.json`` (#289)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.regime_behaviour.evaluator import BEHAVIOUR_PROFILE_FILENAME


class BehaviourArtifactError(Exception):
    """Overwrite or seal failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def write_behaviour_profile_artifact(
    directory: Path, artifact: dict[str, Any]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / BEHAVIOUR_PROFILE_FILENAME
    if target.exists():
        raise BehaviourArtifactError(
            f"refusing to overwrite existing behaviour profile: {target}"
        )
    payload = _canonical_json_bytes(artifact)
    digest = hashlib.sha256(payload).hexdigest()
    tmp = directory / f".{BEHAVIOUR_PROFILE_FILENAME}.tmp"
    tmp.write_bytes(payload)
    tmp.replace(target)
    (directory / f"{BEHAVIOUR_PROFILE_FILENAME}.sha256").write_text(
        f"{digest}  {BEHAVIOUR_PROFILE_FILENAME}\n", encoding="utf-8"
    )
    return target


def verify_behaviour_profile_seal(directory: Path) -> str:
    target = directory / BEHAVIOUR_PROFILE_FILENAME
    seal = directory / f"{BEHAVIOUR_PROFILE_FILENAME}.sha256"
    if not target.is_file() or not seal.is_file():
        raise BehaviourArtifactError(
            f"missing behaviour profile or seal under {directory}"
        )
    expected = seal.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise BehaviourArtifactError(
            f"behaviour profile seal mismatch: expected {expected}, got {actual}"
        )
    return actual
