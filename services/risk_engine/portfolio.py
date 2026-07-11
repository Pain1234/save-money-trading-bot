"""Portfolio risk calculations — Risk Spec §4."""

from __future__ import annotations

from decimal import Decimal

from risk_engine.models import PortfolioRiskSnapshot, PositionState


def effective_stop(stop_initial: Decimal, trail_stop: Decimal) -> Decimal:
    return max(stop_initial, trail_stop)


def open_risk_usd(position: PositionState) -> Decimal:
    """OpenRiskUSD_i = PositionSize × max(0, EntryPrice − EffectiveStop)."""
    eff = effective_stop(position.stop_initial, position.trail_stop)
    distance = max(Decimal("0"), position.entry_price - eff)
    return position.position_size * distance


def current_open_risk_usd(positions: tuple[PositionState, ...]) -> Decimal:
    return sum((open_risk_usd(p) for p in positions), Decimal("0"))


def total_notional_usd(positions: tuple[PositionState, ...]) -> Decimal:
    return sum((p.position_size * p.mark_price for p in positions), Decimal("0"))


def build_portfolio_snapshot(
    *,
    equity_usd: Decimal,
    positions: tuple[PositionState, ...],
    new_entry_price: Decimal,
    new_quantity: Decimal,
    new_stop_distance: Decimal,
) -> PortfolioRiskSnapshot:
    current = current_open_risk_usd(positions)
    actual_new_risk = new_quantity * new_stop_distance
    projected = current + actual_new_risk
    total_notional = total_notional_usd(positions)
    projected_notional = total_notional + (new_quantity * new_entry_price)
    equity = equity_usd if equity_usd > 0 else Decimal("1")
    return PortfolioRiskSnapshot(
        current_open_risk_usd=current,
        current_open_risk_pct=current / equity,
        projected_portfolio_risk_usd=projected,
        projected_portfolio_risk_pct=projected / equity,
        total_notional_usd=total_notional,
        projected_notional_usd=projected_notional,
        effective_leverage=projected_notional / equity,
    )
