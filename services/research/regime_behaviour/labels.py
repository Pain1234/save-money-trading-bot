"""Deterministic behaviour labels from regime metric rows (#289)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from research.regime_behaviour.policy import BehaviourPolicy

BEHAVIOUR_LABELS: frozenset[str] = frozenset(
    {
        "PROFITABLE",
        "DEFENSIVE_INACTIVE",
        "CONTROLLED_BLEED",
        "WHIPSAW_PRONE",
        "LATE_EXIT",
        "LATE_ENTRY",
        "OVERACTIVE_REENTRY",
        "COST_INTENSIVE",
        "TAIL_RISK_EXPOSED",
        "SHOCK_DEPENDENT",
        "INSUFFICIENT_EVIDENCE",
    }
)

# Priority for main_weakness (first match wins among present labels).
_WEAKNESS_PRIORITY: tuple[str, ...] = (
    "TAIL_RISK_EXPOSED",
    "WHIPSAW_PRONE",
    "SHOCK_DEPENDENT",
    "COST_INTENSIVE",
    "OVERACTIVE_REENTRY",
    "LATE_EXIT",
    "LATE_ENTRY",
    "CONTROLLED_BLEED",
    "INSUFFICIENT_EVIDENCE",
)

_STRENGTH_PRIORITY: tuple[str, ...] = (
    "PROFITABLE",
    "DEFENSIVE_INACTIVE",
)


def _dec(value: object | None, default: str = "0") -> Decimal:
    if value is None or value == "NOT_AVAILABLE":
        return Decimal(default)
    return Decimal(str(value))


def _optional_dec(value: object | None) -> Decimal | None:
    if value is None or value == "NOT_AVAILABLE":
        return None
    return Decimal(str(value))


def derive_regime_labels(
    regime_row: Mapping[str, Any],
    policy: BehaviourPolicy,
) -> tuple[str, ...]:
    """Return sorted unique labels for one regime_metrics regimes[] row."""
    labels: set[str] = set()
    status = str(regime_row.get("status") or "")
    trend = str(regime_row.get("trend") or "")
    zero = bool(regime_row.get("zero_activity"))
    trades = int(regime_row.get("closed_trades") or 0)
    net = _dec(regime_row.get("net_pnl"))
    costs = regime_row.get("costs") if isinstance(regime_row.get("costs"), dict) else {}
    fee = _dec(costs.get("fees") if isinstance(costs, dict) else None)
    slip = _dec(costs.get("slippage_costs") if isinstance(costs, dict) else None)
    fund = _dec(costs.get("funding_costs") if isinstance(costs, dict) else None)
    total_cost = fee + slip + fund
    expectancy = _optional_dec(regime_row.get("expectancy"))
    tail = _optional_dec(regime_row.get("tail_loss"))
    concentration = _optional_dec(regime_row.get("pnl_concentration"))
    time_in_market = _optional_dec(regime_row.get("time_in_market"))

    if status in ("INSUFFICIENT_EVIDENCE",) or trend == "INSUFFICIENT":
        return ("INSUFFICIENT_EVIDENCE",)

    # Trend-following: zero trades is not automatic failure.
    if zero or trades == 0:
        labels.add("DEFENSIVE_INACTIVE")
        return tuple(sorted(labels))

    if net >= Decimal(policy.profitable_net_min):
        labels.add("PROFITABLE")
    elif net >= Decimal(policy.controlled_bleed_net_min):
        labels.add("CONTROLLED_BLEED")

    denom = max(abs(net), Decimal("1"))
    if total_cost / denom >= Decimal(policy.cost_intensive_ratio):
        labels.add("COST_INTENSIVE")

    if (
        trades >= policy.whipsaw_min_trades
        and expectancy is not None
        and expectancy <= 0
        and net < 0
    ):
        labels.add("WHIPSAW_PRONE")

    if tail is not None and tail >= Decimal(policy.tail_risk_min):
        labels.add("TAIL_RISK_EXPOSED")

    if (
        concentration is not None
        and concentration >= Decimal(policy.shock_concentration_min)
        and net < 0
    ):
        labels.add("SHOCK_DEPENDENT")

    # Heuristics for late entry/exit using exposure/time proxies (documented).
    if trend in ("BULL", "BEAR") and time_in_market is not None:
        if time_in_market < Decimal("0.1") and net <= 0:
            labels.add("LATE_ENTRY")
        if time_in_market > Decimal("0.85") and net < 0:
            labels.add("LATE_EXIT")

    if trades >= policy.whipsaw_min_trades * 2 and net <= 0:
        labels.add("OVERACTIVE_REENTRY")

    if not labels:
        labels.add("INSUFFICIENT_EVIDENCE")
    return tuple(sorted(labels))


def pick_main_weakness(labels: tuple[str, ...]) -> str | None:
    present = set(labels)
    for candidate in _WEAKNESS_PRIORITY:
        if candidate in present:
            return candidate
    return None


def pick_main_strength(labels: tuple[str, ...]) -> str | None:
    present = set(labels)
    for candidate in _STRENGTH_PRIORITY:
        if candidate in present:
            return candidate
    return None
