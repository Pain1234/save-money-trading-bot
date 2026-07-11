"""Shared pure lifecycle calculations for backtester and paper trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from risk_engine.engine import RiskEngine
from risk_engine.models import (
    BotSystemState,
    MarketDataStatus,
    RiskDecision,
    RiskParameters,
    SymbolConstraints,
    TradeProposal,
    TradeSide,
)
from strategy_engine.models import (
    Candle,
    ReasonCode,
    SignalIntentKind,
    StrategyParameters,
    TrailingStopState,
)
from strategy_engine.stops import (
    compute_initial_stop,
    initialize_trailing_stop,
    update_trailing_stop,
)

from backtester.execution import (
    apply_entry_slippage,
    apply_exit_slippage,
    compute_fee,
    compute_slippage_cost,
)
from backtester.models import ExitReason, PendingIntent, SimulatedPosition, SlippageModel
from backtester.portfolio import (
    build_account_state,
    build_portfolio_state,
    position_margin,
    resolve_marks_at_open,
    to_open_orders,
    to_position_states,
)


@dataclass(frozen=True)
class EntryFillComputation:
    open_ref: Decimal
    fill_price: Decimal
    stop_initial: Decimal
    slippage_cost: Decimal


@dataclass(frozen=True)
class EntryAccounting:
    quantity: Decimal
    notional: Decimal
    fee: Decimal
    slippage_cost: Decimal
    margin_reserved: Decimal
    initial_risk_usd: Decimal
    trail_state: TrailingStopState


@dataclass(frozen=True)
class StopTriggerResult:
    exit_reference: Decimal
    exit_reason: ExitReason


@dataclass(frozen=True)
class ExitAccounting:
    fill_price: Decimal
    fee: Decimal
    slippage_cost: Decimal
    gross_pnl: Decimal
    net_wallet_delta: Decimal


def slippage_model_from_bps(slippage_bps: Decimal) -> SlippageModel:
    return SlippageModel(slippage_bps=slippage_bps)


def compute_entry_fill_prices(
    open_ref: Decimal,
    atr14: Decimal,
    *,
    slippage_bps: Decimal,
    strategy_params: StrategyParameters,
    price_tick_size: Decimal,
) -> EntryFillComputation:
    """Apply entry slippage and compute fill-based initial stop."""
    model = slippage_model_from_bps(slippage_bps)
    fill_price = apply_entry_slippage(open_ref, model)
    stop_initial = compute_initial_stop(fill_price, atr14, strategy_params, price_tick_size)
    slip_cost = compute_slippage_cost(open_ref, fill_price, Decimal("1"))
    return EntryFillComputation(
        open_ref=open_ref,
        fill_price=fill_price,
        stop_initial=stop_initial,
        slippage_cost=slip_cost,
    )


def evaluate_entry_risk_decision(
    risk_engine: RiskEngine,
    *,
    symbol: str,
    fill_price: Decimal,
    stop_initial: Decimal,
    client_intent_id: str,
    atr14: Decimal,
    constraints: SymbolConstraints,
    wallet_cash: Decimal,
    open_positions: tuple[SimulatedPosition, ...],
    pending_intents: tuple[PendingIntent, ...],
    processed_intent_ids: frozenset[str],
    day_candles: dict[str, Candle],
    prior_closes: dict[str, Decimal],
    risk_params: RiskParameters,
    market_data_status: MarketDataStatus = MarketDataStatus.OK,
    bot_system_state: BotSystemState = BotSystemState.ACTIVE,
) -> RiskDecision:
    """Run RiskEngine for a post-slippage entry fill."""
    marks = resolve_marks_at_open(open_positions, day_candles, prior_closes)
    portfolio = build_portfolio_state(wallet_cash, open_positions)
    account = build_account_state(portfolio, marks, risk_params.max_leverage)
    proposal = TradeProposal(
        symbol=symbol,
        side=TradeSide.LONG,
        entry_price=fill_price,
        stop_price=stop_initial,
        client_intent_id=client_intent_id,
        signal_intent_kind=SignalIntentKind.LONG_ENTRY,
        strategy_approved=True,
        market_data_status=market_data_status,
        bot_system_state=bot_system_state,
        atr14=atr14,
    )
    return risk_engine.evaluate(
        proposal,
        account,
        constraints,
        open_positions=to_position_states(open_positions, marks),
        open_orders=to_open_orders(pending_intents),
        processed_intent_ids=processed_intent_ids,
        params=risk_params,
    )


def compute_entry_accounting(
    *,
    fill_price: Decimal,
    open_ref: Decimal,
    quantity: Decimal,
    stop_initial: Decimal,
    fee_rate: Decimal,
    slippage_bps: Decimal,
    max_leverage: Decimal,
    strategy_params: StrategyParameters,
    price_tick_size: Decimal,
    atr14: Decimal,
) -> EntryAccounting:
    """Compute fees, margin, and trailing stop initialization for an approved entry."""
    notional = fill_price * quantity
    fee = compute_fee(notional, fee_rate)
    slip = compute_slippage_cost(open_ref, fill_price, quantity)
    margin = position_margin(notional, max_leverage)
    trail_state = initialize_trailing_stop(
        fill_price, atr14, stop_initial, strategy_params, price_tick_size
    )
    initial_risk = quantity * (fill_price - stop_initial)
    return EntryAccounting(
        quantity=quantity,
        notional=notional,
        fee=fee,
        slippage_cost=slip,
        margin_reserved=margin,
        initial_risk_usd=initial_risk,
        trail_state=trail_state,
    )


def filter_rejection_reason_codes(decision: RiskDecision) -> tuple[ReasonCode, ...]:
    return tuple(c for c in decision.reason_codes if c != ReasonCode.RC_RISK_APPROVED) or (
        decision.reason_codes
    )


def compute_stop_trigger(
    candle: Candle,
    *,
    effective_stop: Decimal,
    initial_stop: Decimal,
    trail_stop: Decimal,
) -> StopTriggerResult | None:
    """Gap stop first, then intraday stop (backtester semantics)."""
    if candle.open < effective_stop:
        return StopTriggerResult(exit_reference=candle.open, exit_reason=ExitReason.STOP_GAP)
    if candle.low <= effective_stop:
        reason = (
            ExitReason.STOP_TRAILING
            if trail_stop >= initial_stop
            else ExitReason.STOP_INITIAL
        )
        return StopTriggerResult(exit_reference=effective_stop, exit_reason=reason)
    return None


def compute_exit_accounting(
    *,
    exit_reference: Decimal,
    quantity: Decimal,
    entry_price: Decimal,
    slippage_bps: Decimal,
    fee_rate: Decimal,
) -> ExitAccounting:
    model = slippage_model_from_bps(slippage_bps)
    fill_price = apply_exit_slippage(exit_reference, model)
    notional = fill_price * quantity
    fee = compute_fee(notional, fee_rate)
    slip = compute_slippage_cost(exit_reference, fill_price, quantity)
    gross = (fill_price - entry_price) * quantity
    net_delta = gross - fee
    return ExitAccounting(
        fill_price=fill_price,
        fee=fee,
        slippage_cost=slip,
        gross_pnl=gross,
        net_wallet_delta=net_delta,
    )


def compute_trailing_stop_update(
    state: TrailingStopState,
    daily_close: Decimal,
    atr14: Decimal,
    strategy_params: StrategyParameters,
    price_tick_size: Decimal,
) -> TrailingStopState:
    """Update trailing stop on daily close; never lowers stop."""
    return update_trailing_stop(
        state,
        daily_close,
        atr14,
        strategy_params,
        price_tick_size,
    )


def build_simulated_position_from_entry(
    *,
    symbol: str,
    quantity: Decimal,
    fill_price: Decimal,
    entry_time: datetime,
    accounting: EntryAccounting,
    atr14: Decimal,
    client_intent_id: str,
) -> SimulatedPosition:
    trail = accounting.trail_state
    return SimulatedPosition(
        symbol=symbol,
        quantity=quantity,
        entry_price=fill_price,
        entry_time=entry_time,
        initial_stop=trail.stop_initial,
        trail_stop=trail.trail_stop,
        effective_stop=trail.effective_stop,
        highest_close=trail.highest_close,
        entry_atr14=atr14,
        client_intent_id=client_intent_id,
        margin_reserved=accounting.margin_reserved,
    )
