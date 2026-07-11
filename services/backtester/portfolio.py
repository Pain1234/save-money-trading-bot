"""Portfolio helpers, perpetual accounting, and risk engine mapping."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from risk_engine.models import AccountState, OpenOrderState, PositionState, TradeSide
from risk_engine.portfolio import current_open_risk_usd
from strategy_engine.models import Candle

from backtester.models import PendingIntent, PortfolioState, SimulatedPosition


def mark_prices_from_candles(
    positions: tuple[SimulatedPosition, ...],
    closes: dict[str, Decimal],
) -> dict[str, Decimal]:
    """End-of-day marks from daily close prices."""
    return {p.symbol: closes.get(p.symbol, p.entry_price) for p in positions}


def resolve_marks_at_open(
    positions: tuple[SimulatedPosition, ...],
    day_candles: dict[str, Candle],
    prior_closes: dict[str, Decimal],
) -> dict[str, Decimal]:
    """
    Marks for risk evaluation at the daily open.

    Uses the current bar open when available; otherwise the last known close.
    Never uses the same-day close (not yet known at open).
    """
    marks: dict[str, Decimal] = {}
    for pos in positions:
        candle = day_candles.get(pos.symbol)
        if candle is not None:
            marks[pos.symbol] = candle.open
        elif pos.symbol in prior_closes:
            marks[pos.symbol] = prior_closes[pos.symbol]
        else:
            marks[pos.symbol] = pos.entry_price
    return marks


def compute_used_margin(positions: tuple[SimulatedPosition, ...]) -> Decimal:
    return sum((p.margin_reserved for p in positions), Decimal("0"))


def compute_unrealized_pnl(
    positions: tuple[SimulatedPosition, ...],
    mark_prices: dict[str, Decimal],
) -> Decimal:
    total = Decimal("0")
    for pos in positions:
        mark = mark_prices.get(pos.symbol, pos.entry_price)
        total += pos.quantity * (mark - pos.entry_price)
    return total


def compute_equity(
    wallet_balance: Decimal,
    positions: tuple[SimulatedPosition, ...],
    mark_prices: dict[str, Decimal],
) -> Decimal:
    """Perpetual equity = wallet balance + unrealized PnL."""
    return wallet_balance + compute_unrealized_pnl(positions, mark_prices)


def compute_available_margin(
    wallet_balance: Decimal,
    positions: tuple[SimulatedPosition, ...],
    mark_prices: dict[str, Decimal],
) -> Decimal:
    equity = compute_equity(wallet_balance, positions, mark_prices)
    used = compute_used_margin(positions)
    return max(Decimal("0"), equity - used)


def position_margin(notional: Decimal, max_leverage: Decimal) -> Decimal:
    if max_leverage <= 0:
        return notional
    return notional / max_leverage


def to_position_states(
    positions: tuple[SimulatedPosition, ...],
    mark_prices: dict[str, Decimal],
) -> tuple[PositionState, ...]:
    states: list[PositionState] = []
    for p in positions:
        mark = mark_prices.get(p.symbol, p.entry_price)
        if p.quantity <= 0 or mark <= 0:
            continue
        states.append(
            PositionState(
                symbol=p.symbol,
                entry_price=p.entry_price,
                position_size=p.quantity,
                stop_initial=p.initial_stop,
                trail_stop=p.trail_stop,
                mark_price=mark,
            )
        )
    return tuple(states)


def to_open_orders(pending: tuple[PendingIntent, ...]) -> tuple[OpenOrderState, ...]:
    return tuple(
        OpenOrderState(
            symbol=i.symbol,
            client_intent_id=i.client_intent_id,
            side=TradeSide.LONG,
            is_entry=True,
        )
        for i in pending
    )


def build_portfolio_state(
    wallet_balance: Decimal,
    positions: tuple[SimulatedPosition, ...],
    *,
    pending_intents: tuple[PendingIntent, ...] = (),
    total_fees: Decimal = Decimal("0"),
    total_funding: Decimal = Decimal("0"),
    total_slippage: Decimal = Decimal("0"),
    realized_pnl: Decimal = Decimal("0"),
) -> PortfolioState:
    return PortfolioState(
        cash=wallet_balance,
        positions=positions,
        pending_intents=pending_intents,
        total_fees=total_fees,
        total_funding=total_funding,
        total_slippage=total_slippage,
        realized_pnl=realized_pnl,
    )


def build_account_state(
    portfolio: PortfolioState,
    mark_prices: dict[str, Decimal],
    max_leverage: Decimal,
) -> AccountState:
    equity = portfolio.equity_usd(mark_prices)
    used = portfolio.used_margin_usd()
    available = max(Decimal("0"), equity - used)
    return AccountState(
        equity_usd=equity,
        available_margin_usd=available,
        peak_equity_usd=equity,
    )


def current_open_risk(
    positions: tuple[SimulatedPosition, ...],
    marks: dict[str, Decimal],
) -> Decimal:
    return current_open_risk_usd(to_position_states(positions, marks))


def prior_closes_from_timeline(
    daily_by_sym: dict[str, dict[datetime, tuple[int, Candle]]],
    symbols: tuple[str, ...],
    before_open: datetime,
) -> dict[str, Decimal]:
    """Last fully closed daily close strictly before ``before_open``."""
    result: dict[str, Decimal] = {}
    for sym in symbols:
        by_time = daily_by_sym.get(sym, {})
        prior: datetime | None = None
        for ot in by_time:
            if ot < before_open and (prior is None or ot > prior):
                prior = ot
        if prior is not None:
            result[sym] = by_time[prior][1].close
    return result
