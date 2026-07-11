"""Position sizing — Risk Spec §3."""

from __future__ import annotations

from decimal import Decimal

from risk_engine.models import PositionSizingResult, RiskParameters
from risk_engine.rounding import floor_to_step


def compute_stop_distance(entry_price: Decimal, stop_price: Decimal) -> Decimal:
    return entry_price - stop_price


def compute_risk_budget(equity_usd: Decimal, params: RiskParameters) -> Decimal:
    return equity_usd * params.risk_per_trade_pct


def compute_raw_quantity(risk_budget_usd: Decimal, stop_distance_usd: Decimal) -> Decimal:
    return risk_budget_usd / stop_distance_usd


def apply_risk_cap_after_rounding(
    quantity: Decimal,
    *,
    stop_distance_usd: Decimal,
    equity_usd: Decimal,
    risk_budget_usd: Decimal,
    quantity_step: Decimal,
    minimum_quantity: Decimal,
    params: RiskParameters,
) -> Decimal | None:
    """
    Reduce quantity until ActualRiskUSD ≤ RiskBudgetUSD and within pct tolerance.

    Risk Spec §3.4 — rounding may only reduce risk, never increase above limit.
    """
    qty = quantity
    trade_limit = params.risk_per_trade_pct * (Decimal("1") + params.risk_rounding_tolerance)

    while qty >= minimum_quantity:
        actual_risk = qty * stop_distance_usd
        actual_pct = actual_risk / equity_usd
        if actual_risk <= risk_budget_usd and actual_pct <= trade_limit:
            return qty
        next_qty = floor_to_step(qty - quantity_step, quantity_step)
        if next_qty == qty:
            break
        qty = next_qty

    return None


def compute_position_sizing(
    *,
    equity_usd: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    quantity_step: Decimal,
    minimum_quantity: Decimal,
    params: RiskParameters,
) -> PositionSizingResult | None:
    stop_distance = compute_stop_distance(entry_price, stop_price)
    if stop_distance <= 0:
        return None

    risk_budget = compute_risk_budget(equity_usd, params)
    raw_qty = compute_raw_quantity(risk_budget, stop_distance)
    rounded = floor_to_step(raw_qty, quantity_step)

    if rounded <= 0:
        return PositionSizingResult(
            risk_budget_usd=risk_budget,
            stop_distance_usd=stop_distance,
            raw_quantity=raw_qty,
            rounded_quantity=Decimal("0"),
            actual_trade_risk_usd=Decimal("0"),
            actual_trade_risk_pct=Decimal("0"),
        )

    final_qty = apply_risk_cap_after_rounding(
        rounded,
        stop_distance_usd=stop_distance,
        equity_usd=equity_usd,
        risk_budget_usd=risk_budget,
        quantity_step=quantity_step,
        minimum_quantity=minimum_quantity,
        params=params,
    )
    if final_qty is None:
        return PositionSizingResult(
            risk_budget_usd=risk_budget,
            stop_distance_usd=stop_distance,
            raw_quantity=raw_qty,
            rounded_quantity=Decimal("0"),
            actual_trade_risk_usd=Decimal("0"),
            actual_trade_risk_pct=Decimal("0"),
        )

    actual_risk = final_qty * stop_distance
    return PositionSizingResult(
        risk_budget_usd=risk_budget,
        stop_distance_usd=stop_distance,
        raw_quantity=raw_qty,
        rounded_quantity=final_qty,
        actual_trade_risk_usd=actual_risk,
        actual_trade_risk_pct=actual_risk / equity_usd,
    )


def cap_quantity_for_leverage(
    quantity: Decimal,
    *,
    entry_price: Decimal,
    equity_usd: Decimal,
    total_notional_usd: Decimal,
    quantity_step: Decimal,
    max_leverage: Decimal,
) -> Decimal:
    """Risk Spec §6.2 — leverage may only reduce size."""
    projected_notional = total_notional_usd + (quantity * entry_price)
    projected_leverage = projected_notional / equity_usd
    if projected_leverage <= max_leverage:
        return quantity

    max_new_notional = (max_leverage * equity_usd) - total_notional_usd
    if max_new_notional <= 0:
        return Decimal("0")
    capped = floor_to_step(max_new_notional / entry_price, quantity_step)
    return min(quantity, capped)


def cap_quantity_for_margin(
    quantity: Decimal,
    *,
    entry_price: Decimal,
    available_margin_usd: Decimal,
    max_leverage: Decimal,
    quantity_step: Decimal,
) -> Decimal:
    """Reduce size when required margin exceeds available margin."""
    if available_margin_usd < 0:
        return Decimal("0")
    notional = quantity * entry_price
    required_margin = notional / max_leverage
    if required_margin <= available_margin_usd:
        return quantity

    max_notional = available_margin_usd * max_leverage
    if max_notional <= 0:
        return Decimal("0")
    return min(quantity, floor_to_step(max_notional / entry_price, quantity_step))
