"""Transition-risk profile from regime_labels transitions (#289)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from research.regime_behaviour.policy import BehaviourPolicy


def _dec(value: object | None) -> Decimal:
    if value is None or value == "NOT_AVAILABLE":
        return Decimal("0")
    return Decimal(str(value))


def _optional_dec(value: object | None) -> Decimal | None:
    if value is None or value == "NOT_AVAILABLE":
        return None
    return Decimal(str(value))


def build_transition_risk_profile(
    *,
    transitions: Sequence[Mapping[str, Any]],
    day_events: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]] | None = None,
    policy: BehaviourPolicy,
    evidence_trusted: bool = True,
) -> dict[str, Any]:
    """Deterministic transition risk summary (no LLM).

    Uses classifier transition records + TRANSITION_IN/OUT day tags.
    Optional trades attributed by exit day event for cost/turnover in windows.
    Turnover = quantity × entry_fill_price (same convention as regime quality).
    """
    if not evidence_trusted:
        return {
            "transition_count": len(transitions),
            "transition_id_counts": {},
            "transition_in_days": 0,
            "transition_out_days": 0,
            "stable_days": 0,
            "window_closed_trades": 0,
            "window_net_pnl": "NOT_AVAILABLE",
            "window_costs": "NOT_AVAILABLE",
            "window_turnover": "NOT_AVAILABLE",
            "risk_label": "INSUFFICIENT_EVIDENCE",
            "mae": "NOT_AVAILABLE",
            "time_to_derisk": "NOT_AVAILABLE",
        }

    transition_ids = [str(t.get("transition_id") or "") for t in transitions]
    counts: dict[str, int] = defaultdict(int)
    for tid in transition_ids:
        if tid:
            counts[tid] += 1

    in_days = sum(1 for e in day_events if e.get("event") == "TRANSITION_IN")
    out_days = sum(1 for e in day_events if e.get("event") == "TRANSITION_OUT")
    stable_days = sum(1 for e in day_events if e.get("event") == "STABLE_REGIME")

    event_by_day = {
        str(e.get("as_of")): str(e.get("event") or "")
        for e in day_events
        if e.get("as_of")
    }
    window_trades = 0
    window_net = Decimal("0")
    window_costs = Decimal("0")
    window_turnover = Decimal("0")
    if trades:
        for trade in trades:
            exit_time = trade.get("exit_time")
            if exit_time is None:
                continue
            day = str(exit_time)[:10]
            event = event_by_day.get(day)
            if event not in ("TRANSITION_IN", "TRANSITION_OUT"):
                continue
            window_trades += 1
            if trade.get("net_pnl") is not None:
                window_net += _dec(trade.get("net_pnl"))
            costs = (
                _dec(trade.get("fees"))
                + _dec(trade.get("slippage_cost"))
                + _dec(trade.get("funding"))
            )
            window_costs += costs
            qty = _optional_dec(trade.get("quantity"))
            entry = _optional_dec(trade.get("entry_fill_price"))
            if qty is not None and entry is not None:
                window_turnover += abs(qty) * entry

    n_transitions = len(transitions)
    high_count = policy.high_transition_count_min
    high_net_floor = Decimal(policy.high_transition_window_net_max)
    if n_transitions == 0 and in_days + out_days == 0:
        risk_label = "INSUFFICIENT_EVIDENCE"
    elif n_transitions >= high_count or window_net < high_net_floor:
        risk_label = "HIGH_TRANSITION_RISK"
    elif n_transitions >= 1:
        risk_label = "MODERATE_TRANSITION_RISK"
    else:
        risk_label = "LOW_TRANSITION_RISK"

    return {
        "transition_count": n_transitions,
        "transition_id_counts": dict(sorted(counts.items())),
        "transition_in_days": in_days,
        "transition_out_days": out_days,
        "stable_days": stable_days,
        "window_closed_trades": window_trades,
        "window_net_pnl": format(window_net, "f"),
        "window_costs": format(window_costs, "f"),
        "window_turnover": format(window_turnover, "f"),
        "risk_label": risk_label,
        "mae": "NOT_AVAILABLE",  # requires tick path; explicit N/A
        "time_to_derisk": "NOT_AVAILABLE",
    }
