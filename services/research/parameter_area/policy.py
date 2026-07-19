"""Versioned parameter-area / plateau policy (#290).

Public illustrative thresholds — not private Strategy V1 numbers.
All classification cutoffs live here so content-hash fails closed on silent edits.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


class ParameterAreaPolicyError(Exception):
    """Unknown policy version or content-hash mismatch."""


PARAMETER_AREA_LABELS: tuple[str, ...] = (
    "BROAD_STABLE_PLATEAU",
    "NARROW_STABLE_AREA",
    "ISOLATED_PEAK",
    "UNSTABLE",
    "INSUFFICIENT_EVIDENCE",
)


@dataclass(frozen=True)
class ParameterAreaPolicy:
    version: str
    description: str
    # Minimum complete neighbor observations (excluding frozen) for any
    # classification stronger than INSUFFICIENT_EVIDENCE.
    min_complete_neighbors: int
    # Neighbor "positive" / PnL floor (Decimal-as-string).
    min_net_pnl: str
    # Cost stability: total_costs / max(|net_pnl|, 1) must be <= this ratio.
    max_cost_ratio: str
    # Contiguous stable region sizes (including frozen when frozen is stable).
    broad_min_contiguous: int
    narrow_min_contiguous: int
    # Steepest local drop (frozen_net - neighbor_net) above this → UNSTABLE
    # when pass ratios are also weak (see classifier).
    steep_drop_warn: str
    # Share of complete neighbors that are stable for BROAD / not UNSTABLE.
    broad_min_stable_share: str
    narrow_min_stable_share: str
    # BROAD additionally requires gate evidence with share >= this.
    broad_min_gate_pass_share: str
    # Contiguity rule id (documented; hashed).
    contiguity_rule: str

    def to_dict(self) -> dict[str, object]:
        return {
            "broad_min_contiguous": self.broad_min_contiguous,
            "broad_min_gate_pass_share": self.broad_min_gate_pass_share,
            "broad_min_stable_share": self.broad_min_stable_share,
            "contiguity_rule": self.contiguity_rule,
            "description": self.description,
            "max_cost_ratio": self.max_cost_ratio,
            "min_complete_neighbors": self.min_complete_neighbors,
            "min_net_pnl": self.min_net_pnl,
            "narrow_min_contiguous": self.narrow_min_contiguous,
            "narrow_min_stable_share": self.narrow_min_stable_share,
            "steep_drop_warn": self.steep_drop_warn,
            "version": self.version,
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_policy_content_hash(policy: ParameterAreaPolicy) -> str:
    return hashlib.sha256(_canonical_json_bytes(policy.to_dict())).hexdigest()


_POLICY_REGISTRY: dict[str, ParameterAreaPolicy] = {
    "1.0": ParameterAreaPolicy(
        version="1.0",
        description=(
            "OAT (#247) parameter-area classification. Stable neighbors require "
            "complete status, net_pnl floor, and cost-ratio bound; profit alone "
            "is insufficient. BROAD also requires gate-pass share. Contiguity = "
            "adjacent steps on a single OAT axis including the frozen point."
        ),
        min_complete_neighbors=2,
        min_net_pnl="0",
        max_cost_ratio="0.5",
        broad_min_contiguous=3,
        narrow_min_contiguous=2,
        steep_drop_warn="50",
        broad_min_stable_share="0.6",
        narrow_min_stable_share="0.35",
        broad_min_gate_pass_share="0.5",
        contiguity_rule="oat_axis_adjacent_including_frozen_v1",
    ),
}


def get_parameter_area_policy(version: str) -> ParameterAreaPolicy:
    try:
        return _POLICY_REGISTRY[version]
    except KeyError as exc:
        raise ParameterAreaPolicyError(
            f"unknown parameter-area policy version: {version!r}"
        ) from exc


def verify_parameter_area_policy_content_hash(
    version: str, expected_hash: str
) -> None:
    policy = get_parameter_area_policy(version)
    actual = compute_policy_content_hash(policy)
    if actual != expected_hash:
        raise ParameterAreaPolicyError(
            f"parameter-area policy content hash mismatch for {version!r}: "
            f"expected {expected_hash}, got {actual}"
        )
