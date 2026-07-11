"""Portfolio accounting adapters for paper trading persistence."""

from __future__ import annotations

from decimal import Decimal

from backtester.models import SimulatedPosition
from backtester.portfolio import (
    build_account_state,
    build_portfolio_state,
    compute_equity,
    compute_unrealized_pnl,
    compute_used_margin,
    resolve_marks_at_open,
    to_position_states,
)
from risk_engine.models import AccountState, RiskParameters
from risk_engine.portfolio import current_open_risk_usd
from strategy_engine.models import Candle

from paper_trading.models import PaperPosition, PaperWalletState


def paper_position_to_simulated(position: PaperPosition) -> SimulatedPosition:
    """Convert a persisted paper position to backtester accounting shape."""
    return SimulatedPosition(
        symbol=position.symbol,
        quantity=position.quantity,
        entry_price=position.average_entry_price,
        entry_time=position.opened_at,
        initial_stop=position.initial_stop,
        trail_stop=position.current_stop,
        effective_stop=position.current_stop,
        highest_close=position.highest_close_since_entry,
        entry_atr14=position.average_entry_price,
        client_intent_id=str(position.entry_intent_id),
        margin_reserved=position.margin_reserved,
    )


def build_account_from_paper_state(
    wallet: PaperWalletState,
    open_positions: tuple[PaperPosition, ...],
    mark_prices: dict[str, Decimal],
    risk_params: RiskParameters,
) -> AccountState:
    simulated = tuple(paper_position_to_simulated(p) for p in open_positions)
    portfolio = build_portfolio_state(
        wallet.cash,
        simulated,
        total_fees=wallet.total_fees,
        total_funding=wallet.total_funding,
        total_slippage=wallet.total_slippage,
        realized_pnl=wallet.total_realized_pnl,
    )
    return build_account_state(portfolio, mark_prices, risk_params.max_leverage)


def compute_paper_equity(
    wallet: PaperWalletState,
    open_positions: tuple[PaperPosition, ...],
    mark_prices: dict[str, Decimal],
) -> Decimal:
    simulated = tuple(paper_position_to_simulated(p) for p in open_positions)
    return compute_equity(wallet.cash, simulated, mark_prices)


def compute_paper_unrealized_pnl(
    open_positions: tuple[PaperPosition, ...],
    mark_prices: dict[str, Decimal],
) -> Decimal:
    simulated = tuple(paper_position_to_simulated(p) for p in open_positions)
    return compute_unrealized_pnl(simulated, mark_prices)


def compute_paper_open_risk(
    open_positions: tuple[PaperPosition, ...],
    mark_prices: dict[str, Decimal],
) -> Decimal:
    simulated = tuple(paper_position_to_simulated(p) for p in open_positions)
    return current_open_risk_usd(to_position_states(simulated, mark_prices))


def compute_paper_margin_used(open_positions: tuple[PaperPosition, ...]) -> Decimal:
    simulated = tuple(paper_position_to_simulated(p) for p in open_positions)
    return compute_used_margin(simulated)


def resolve_marks_for_paper_positions(
    open_positions: tuple[PaperPosition, ...],
    day_candles: dict[str, Candle],
    prior_closes: dict[str, Decimal],
) -> dict[str, Decimal]:
    simulated = tuple(paper_position_to_simulated(p) for p in open_positions)
    return resolve_marks_at_open(simulated, day_candles, prior_closes)
