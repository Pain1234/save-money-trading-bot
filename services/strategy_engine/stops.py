"""ATR stops — Strategy Spec §6, §7."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from strategy_engine.models import StrategyParameters, TrailingStopState


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round price down to tick_size (Long stop direction)."""
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    steps = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return steps * tick_size


def compute_initial_stop(
    entry_price: Decimal,
    atr14: Decimal,
    params: StrategyParameters,
    tick_size: Decimal | None = None,
) -> Decimal:
    """
    StopInitial = EntryPrice − (stop_initial_atr_mult × ATR14).

    Strategy Spec §6.
    """
    stop = entry_price - (params.stop_initial_atr_mult * atr14)
    if tick_size is not None:
        stop = round_to_tick(stop, tick_size)
    return stop


def initialize_trailing_stop(
    entry_price: Decimal,
    atr14_at_entry: Decimal,
    stop_initial: Decimal,
    params: StrategyParameters,
    tick_size: Decimal | None = None,
) -> TrailingStopState:
    """Trailing stop initialization — Strategy Spec §7.2."""
    highest_close = entry_price
    trail_stop = highest_close - (params.trail_atr_mult * atr14_at_entry)
    trail_stop = max(trail_stop, stop_initial)
    if tick_size is not None:
        trail_stop = round_to_tick(trail_stop, tick_size)
    effective = max(stop_initial, trail_stop)
    return TrailingStopState(
        entry_price=entry_price,
        stop_initial=stop_initial,
        highest_close=highest_close,
        trail_stop=trail_stop,
        effective_stop=effective,
    )


def update_trailing_stop(
    state: TrailingStopState,
    close_t: Decimal,
    atr14_daily_t: Decimal,
    params: StrategyParameters,
    tick_size: Decimal | None = None,
) -> TrailingStopState:
    """
    Daily trailing stop update — exact sequence Strategy Spec §7.3.

    1. atr_current  := ATR14_daily[t]
    2. HighestClose := max(HighestClose, C[t])
    3. trail_candidate := HighestClose − (trail_atr_mult × atr_current)
    4. TrailStop    := max(TrailStop, trail_candidate)
    5. TrailStop    := max(TrailStop, StopInitial)
    6. TrailStop    := round_to_tick(TrailStop)
    7. EffectiveStop := max(StopInitial, TrailStop)
    """
    atr_current = atr14_daily_t

    highest_close = max(state.highest_close, close_t)

    trail_candidate = highest_close - (params.trail_atr_mult * atr_current)

    trail_stop = max(state.trail_stop, trail_candidate)

    trail_stop = max(trail_stop, state.stop_initial)

    if tick_size is not None:
        trail_stop = round_to_tick(trail_stop, tick_size)

    effective_stop = max(state.stop_initial, trail_stop)

    return TrailingStopState(
        entry_price=state.entry_price,
        stop_initial=state.stop_initial,
        highest_close=highest_close,
        trail_stop=trail_stop,
        effective_stop=effective_stop,
    )
