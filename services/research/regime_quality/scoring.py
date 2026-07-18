"""Optional versioned quality summary scores (#287).

Scores never replace raw metrics and must not be used as sole decision input.
Missing inputs → NOT_AVAILABLE (never coerced to 0).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from research.regime_quality.availability import NOT_AVAILABLE
from research.regime_quality.metrics import RegimeSliceRaw


@dataclass(frozen=True)
class QualityScorePolicy:
    """Immutable weights for optional 0–10 style summary."""

    version: str
    description: str
    # Weight on normalized net_pnl contribution (illustrative public defaults).
    weight_net_pnl: str
    weight_drawdown: str
    weight_trade_count: str

    def to_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "version": self.version,
            "weight_drawdown": self.weight_drawdown,
            "weight_net_pnl": self.weight_net_pnl,
            "weight_trade_count": self.weight_trade_count,
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_score_policy_content_hash(policy: QualityScorePolicy) -> str:
    return hashlib.sha256(_canonical_json_bytes(policy.to_dict())).hexdigest()


_SCORE_POLICY_REGISTRY: dict[str, QualityScorePolicy] = {
    "1.0": QualityScorePolicy(
        version="1.0",
        description=(
            "Generic illustrative quality summary weights for P4.9. "
            "Not private Strategy V1 thresholds; never sole decision input."
        ),
        weight_net_pnl="0.5",
        weight_drawdown="0.3",
        weight_trade_count="0.2",
    ),
}


def get_score_policy(version: str) -> QualityScorePolicy:
    try:
        return _SCORE_POLICY_REGISTRY[version]
    except KeyError as exc:
        raise KeyError(f"unknown quality score policy version: {version!r}") from exc


def summarize_slice_score(
    slice_raw: RegimeSliceRaw,
    *,
    policy: QualityScorePolicy,
    net_pnl_scale: Decimal = Decimal("1000"),
) -> dict[str, Any]:
    """Return versioned summary; NOT_AVAILABLE when evidence insufficient."""
    policy_hash = compute_score_policy_content_hash(policy)
    base = {
        "score_policy_version": policy.version,
        "score_policy_content_hash": policy_hash,
        "decision_binding": False,
        "note": "summary_only_raw_metrics_required",
    }
    if slice_raw.status == "INSUFFICIENT_EVIDENCE":
        return {**base, "score": NOT_AVAILABLE, "reason": "insufficient_evidence"}
    if slice_raw.zero_activity:
        # Zero activity is valid raw evidence; score remains N/A (not zero).
        return {**base, "score": NOT_AVAILABLE, "reason": "zero_activity"}

    # Simple bounded heuristic in [0, 10] for illustration only.
    w_pnl = Decimal(policy.weight_net_pnl)
    w_dd = Decimal(policy.weight_drawdown)
    w_n = Decimal(policy.weight_trade_count)
    pnl_term = min(
        Decimal("10"),
        max(Decimal("0"), (slice_raw.net_pnl / net_pnl_scale) * Decimal("5") + Decimal("5")),
    )
    if slice_raw.max_drawdown is None:
        return {**base, "score": NOT_AVAILABLE, "reason": "max_drawdown_missing"}
    dd_term = max(Decimal("0"), Decimal("10") * (Decimal("1") - slice_raw.max_drawdown))
    n_term = min(Decimal("10"), Decimal(slice_raw.closed_trades))
    score = (w_pnl * pnl_term + w_dd * dd_term + w_n * n_term) / (w_pnl + w_dd + w_n)
    return {
        **base,
        "score": format(score.quantize(Decimal("0.01")), "f"),
        "reason": "ok",
    }
