"""Deterministic behaviour labels from regime metric rows (#289)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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

_TREND_SIDEWAYS = "SIDEWAYS"
_TREND_BULL = "BULL"
_TREND_BEAR = "BEAR"


def _optional_dec(value: object | None) -> Decimal | None:
    if value is None or value == "NOT_AVAILABLE":
        return None
    return Decimal(str(value))


def _cost_dec(value: object | None) -> Decimal:
    """Costs default to 0 when absent; PnL does not use this helper."""
    if value is None or value == "NOT_AVAILABLE":
        return Decimal("0")
    return Decimal(str(value))


def derive_regime_labels(
    regime_row: Mapping[str, Any],
    policy: BehaviourPolicy,
    *,
    evidence_trusted: bool = True,
) -> tuple[str, ...]:
    """Return sorted unique labels for one regime_metrics regimes[] row.

    When ``evidence_trusted`` is false (e.g. global evidence_status INCONCLUSIVE),
    only ``INSUFFICIENT_EVIDENCE`` is emitted — no positive strength labels.
    """
    if not evidence_trusted:
        return ("INSUFFICIENT_EVIDENCE",)

    status = str(regime_row.get("status") or "")
    trend = str(regime_row.get("trend") or "")
    zero = bool(regime_row.get("zero_activity"))
    trades = int(regime_row.get("closed_trades") or 0)

    if status in ("INSUFFICIENT_EVIDENCE",) or trend == "INSUFFICIENT":
        return ("INSUFFICIENT_EVIDENCE",)

    # Trend-following: zero trades is defensive only in SIDEWAYS.
    if zero or trades == 0:
        if trend == _TREND_SIDEWAYS:
            return ("DEFENSIVE_INACTIVE",)
        if trend in (_TREND_BULL, _TREND_BEAR):
            return ("LATE_ENTRY",)
        return ("INSUFFICIENT_EVIDENCE",)

    # Required PnL for active regimes — missing/N/A is not break-even profit.
    net = _optional_dec(regime_row.get("net_pnl"))
    if net is None:
        return ("INSUFFICIENT_EVIDENCE",)

    labels: set[str] = set()
    costs = regime_row.get("costs") if isinstance(regime_row.get("costs"), dict) else {}
    fee = _cost_dec(costs.get("fees") if isinstance(costs, dict) else None)
    slip = _cost_dec(costs.get("slippage_costs") if isinstance(costs, dict) else None)
    fund = _cost_dec(costs.get("funding_costs") if isinstance(costs, dict) else None)
    total_cost = fee + slip + fund
    expectancy = _optional_dec(regime_row.get("expectancy"))
    tail = _optional_dec(regime_row.get("tail_loss"))
    concentration = _optional_dec(regime_row.get("pnl_concentration"))
    time_in_market = _optional_dec(regime_row.get("time_in_market"))

    profitable_floor = Decimal(policy.profitable_net_min)
    if profitable_floor <= 0:
        # Fail closed: policy must document a strictly positive profit floor.
        return ("INSUFFICIENT_EVIDENCE",)

    if net >= profitable_floor:
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

    late_entry_max = Decimal(policy.late_entry_time_in_market_max)
    late_exit_min = Decimal(policy.late_exit_time_in_market_min)
    if trend in (_TREND_BULL, _TREND_BEAR) and time_in_market is not None:
        if time_in_market < late_entry_max and net <= 0:
            labels.add("LATE_ENTRY")
        if time_in_market > late_exit_min and net < 0:
            labels.add("LATE_EXIT")

    reentry_floor = (
        policy.whipsaw_min_trades * policy.overactive_reentry_trade_multiplier
    )
    if trades >= reentry_floor and net <= 0:
        labels.add("OVERACTIVE_REENTRY")

    if not labels:
        labels.add("INSUFFICIENT_EVIDENCE")
    return tuple(sorted(labels))


def pick_main_weakness(
    labels: tuple[str, ...],
    priority: Sequence[str],
) -> str | None:
    present = set(labels)
    for candidate in priority:
        if candidate in present:
            return candidate
    return None


def pick_main_strength(
    labels: tuple[str, ...],
    priority: Sequence[str],
) -> str | None:
    present = set(labels)
    for candidate in priority:
        if candidate in present:
            return candidate
    return None
