"""Versioned scorecard assembly policy (#291 / REGIME_SCORECARD Layer 5).

Assembles pinned layer artifacts into a global evidence profile. Does not
encode private Strategy V1 / P5 thresholds and never auto-promotes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


class ScorecardPolicyError(Exception):
    """Unknown policy version or content-hash mismatch."""


@dataclass(frozen=True)
class ScorecardPolicy:
    version: str
    description: str
    # Layer files required in the run directory (fail closed if missing).
    required_layer_files: tuple[str, ...]
    # Optional layers; missing → limitation / NOT_AVAILABLE in global profile.
    optional_layer_files: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "optional_layer_files": list(self.optional_layer_files),
            "required_layer_files": list(self.required_layer_files),
            "version": self.version,
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_scorecard_policy_content_hash(policy: ScorecardPolicy) -> str:
    return hashlib.sha256(_canonical_json_bytes(policy.to_dict())).hexdigest()


_POLICY_1_0 = ScorecardPolicy(
    version="1.0",
    description=(
        "P4.9 Layer-5 scorecard assembly (#291): pin regime labels/metrics/"
        "behaviour (+ confidence when present or derived), parameter_area "
        "NOT_AVAILABLE until #290. No auto-promotion; no private V1 numbers."
    ),
    required_layer_files=(
        "regime_labels.json",
        "regime_metrics.json",
        "behavior_profile.json",
    ),
    optional_layer_files=(
        "confidence_profile.json",
        "parameter_area.json",
    ),
)

_POLICY_REGISTRY: dict[str, ScorecardPolicy] = {"1.0": _POLICY_1_0}

SCORECARD_POLICY_1_0_CONTENT_HASH = (
    "feb34430dae49a67833e580b99f05c79ba55e46d8af9f32135c35d7b68ab9e4b"
)


def get_scorecard_policy(version: str) -> ScorecardPolicy:
    try:
        return _POLICY_REGISTRY[version]
    except KeyError as exc:
        msg = f"unknown scorecard policy version: {version!r}"
        raise ScorecardPolicyError(msg) from exc


def list_scorecard_policy_versions() -> tuple[str, ...]:
    return tuple(sorted(_POLICY_REGISTRY))


def verify_scorecard_policy_content_hash(version: str, expected: str) -> None:
    policy = get_scorecard_policy(version)
    actual = compute_scorecard_policy_content_hash(policy)
    if actual != expected:
        msg = (
            f"scorecard policy content hash mismatch for version {version!r}: "
            f"persisted={expected!r} current={actual!r}"
        )
        raise ScorecardPolicyError(msg)
