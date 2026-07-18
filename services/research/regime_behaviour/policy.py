"""Versioned behaviour-label policy (#289).

Thresholds are public illustrative defaults — not private Strategy V1 numbers.
Silent edits under the same version fail via content-hash mismatch.
All result-affecting thresholds and priority orders live here.
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
    # PROFITABLE requires a strictly positive documented floor (not break-even).
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
    # Late entry/exit exposure proxies on trend regimes.
    late_entry_time_in_market_max: str
    late_exit_time_in_market_min: str
    # OVERACTIVE_REENTRY when trades >= whipsaw_min_trades * multiplier.
    overactive_reentry_trade_multiplier: int
    # Transition-risk thresholds.
    high_transition_count_min: int
    high_transition_window_net_max: str
    # Ranking priorities (first match wins among present labels).
    weakness_priority: tuple[str, ...]
    strength_priority: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "controlled_bleed_net_min": self.controlled_bleed_net_min,
            "cost_intensive_ratio": self.cost_intensive_ratio,
            "description": self.description,
            "high_transition_count_min": self.high_transition_count_min,
            "high_transition_window_net_max": self.high_transition_window_net_max,
            "late_entry_time_in_market_max": self.late_entry_time_in_market_max,
            "late_exit_time_in_market_min": self.late_exit_time_in_market_min,
            "overactive_reentry_trade_multiplier": (
                self.overactive_reentry_trade_multiplier
            ),
            "profitable_net_min": self.profitable_net_min,
            "shock_concentration_min": self.shock_concentration_min,
            "strength_priority": list(self.strength_priority),
            "tail_risk_min": self.tail_risk_min,
            "version": self.version,
            "weakness_priority": list(self.weakness_priority),
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
            "Not private Strategy V1 thresholds; no LLM; no auto-promotion. "
            "PROFITABLE requires net_pnl >= 0.01 (break-even / missing ≠ profit). "
            "Zero trades: DEFENSIVE_INACTIVE only on SIDEWAYS; BULL/BEAR → LATE_ENTRY."
        ),
        profitable_net_min="0.01",
        controlled_bleed_net_min="-50",
        cost_intensive_ratio="0.35",
        whipsaw_min_trades=5,
        tail_risk_min="0.15",
        shock_concentration_min="0.6",
        late_entry_time_in_market_max="0.1",
        late_exit_time_in_market_min="0.85",
        overactive_reentry_trade_multiplier=2,
        high_transition_count_min=3,
        high_transition_window_net_max="-25",
        weakness_priority=(
            "TAIL_RISK_EXPOSED",
            "WHIPSAW_PRONE",
            "SHOCK_DEPENDENT",
            "COST_INTENSIVE",
            "OVERACTIVE_REENTRY",
            "LATE_EXIT",
            "LATE_ENTRY",
            "CONTROLLED_BLEED",
            "INSUFFICIENT_EVIDENCE",
        ),
        strength_priority=(
            "PROFITABLE",
            "DEFENSIVE_INACTIVE",
        ),
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
