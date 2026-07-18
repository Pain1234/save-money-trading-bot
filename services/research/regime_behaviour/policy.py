"""Versioned behaviour-label policy (#289).

Thresholds are public illustrative defaults — not private Strategy V1 numbers.
Silent edits under the same version fail via content-hash mismatch.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


class BehaviourPolicyError(Exception):
    """Unknown policy version or content-hash mismatch."""


@dataclass(frozen=True)
class BehaviourPolicy:
    version: str
    description: str
    # Net PnL floors (absolute USD on synthetic fixtures / research runs).
    profitable_net_min: str
    controlled_bleed_net_min: str  # more negative than this → not "controlled"
    # Cost intensity: fees+slip+funding over max(|net|, 1).
    cost_intensive_ratio: str
    # Whipsaw: many trades with non-positive expectancy.
    whipsaw_min_trades: int
    # Tail: worst episode return magnitude.
    tail_risk_min: str
    # Shock: single-trade |pnl| share of total abs pnl.
    shock_concentration_min: str

    def to_dict(self) -> dict[str, object]:
        return {
            "controlled_bleed_net_min": self.controlled_bleed_net_min,
            "cost_intensive_ratio": self.cost_intensive_ratio,
            "description": self.description,
            "profitable_net_min": self.profitable_net_min,
            "shock_concentration_min": self.shock_concentration_min,
            "tail_risk_min": self.tail_risk_min,
            "version": self.version,
            "whipsaw_min_trades": self.whipsaw_min_trades,
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_policy_content_hash(policy: BehaviourPolicy) -> str:
    return hashlib.sha256(_canonical_json_bytes(policy.to_dict())).hexdigest()


_POLICY_REGISTRY: dict[str, BehaviourPolicy] = {
    "1.0": BehaviourPolicy(
        version="1.0",
        description=(
            "Generic P4.9 behaviour labels over regime_metrics raw fields. "
            "Not private Strategy V1 thresholds; no LLM; no auto-promotion."
        ),
        profitable_net_min="0",
        controlled_bleed_net_min="-50",
        cost_intensive_ratio="0.35",
        whipsaw_min_trades=5,
        tail_risk_min="0.15",
        shock_concentration_min="0.6",
    ),
}


def get_behaviour_policy(version: str) -> BehaviourPolicy:
    try:
        return _POLICY_REGISTRY[version]
    except KeyError as exc:
        raise BehaviourPolicyError(
            f"unknown behaviour policy version: {version!r}"
        ) from exc


def verify_behaviour_policy_content_hash(version: str, expected_hash: str) -> None:
    policy = get_behaviour_policy(version)
    actual = compute_policy_content_hash(policy)
    if actual != expected_hash:
        raise BehaviourPolicyError(
            f"behaviour policy content hash mismatch for {version!r}: "
            f"expected {expected_hash}, got {actual}"
        )
