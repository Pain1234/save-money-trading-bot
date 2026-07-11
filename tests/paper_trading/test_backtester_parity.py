"""Parity tests between backtester and paper lifecycle calculations."""

from __future__ import annotations

from decimal import Decimal

from backtester.execution import apply_entry_slippage, apply_exit_slippage
from backtester.models import SlippageModel
from backtester.paper_lifecycle import (
    compute_entry_fill_prices,
    compute_exit_accounting,
    compute_stop_trigger,
    compute_trailing_stop_update,
)
from strategy_engine.models import Candle, StrategyParameters, Timeframe, TrailingStopState
from strategy_engine.stops import compute_initial_stop

from tests.paper_trading.conftest_execution import utc_dt


def test_entry_slippage_parity() -> None:
    open_ref = Decimal("50000")
    atr = Decimal("1000")
    params = StrategyParameters()
    tick = Decimal("0.01")
    model = SlippageModel(slippage_bps=Decimal("5"))
    expected_fill = apply_entry_slippage(open_ref, model)
    expected_stop = compute_initial_stop(expected_fill, atr, params, tick)
    result = compute_entry_fill_prices(
        open_ref,
        atr,
        slippage_bps=Decimal("5"),
        strategy_params=params,
        price_tick_size=tick,
    )
    assert result.fill_price == expected_fill
    assert result.stop_initial == expected_stop


def test_exit_slippage_parity() -> None:
    model = SlippageModel(slippage_bps=Decimal("5"))
    ref = Decimal("48000")
    expected = apply_exit_slippage(ref, model)
    result = compute_exit_accounting(
        exit_reference=ref,
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000"),
        slippage_bps=Decimal("5"),
        fee_rate=Decimal("0.0005"),
    )
    assert result.fill_price == expected


def test_gap_stop_parity() -> None:
    candle = Candle(
        symbol="BTC",
        timeframe=Timeframe.DAILY,
        open_time=utc_dt(2024, 1, 17),
        close_time=utc_dt(2024, 1, 17, 23, 59, 59),
        open=Decimal("47000"),
        high=Decimal("48000"),
        low=Decimal("46500"),
        close=Decimal("47500"),
        volume=Decimal("100"),
        is_closed=True,
    )
    trigger = compute_stop_trigger(
        candle,
        effective_stop=Decimal("47500"),
        initial_stop=Decimal("48000"),
        trail_stop=Decimal("47500"),
    )
    assert trigger is not None
    assert trigger.exit_reference == Decimal("47000")


def test_trailing_stop_never_decreases() -> None:
    state = TrailingStopState(
        entry_price=Decimal("50000"),
        stop_initial=Decimal("48000"),
        highest_close=Decimal("52000"),
        trail_stop=Decimal("49000"),
        effective_stop=Decimal("49000"),
    )
    params = StrategyParameters()
    updated = compute_trailing_stop_update(
        state,
        Decimal("51000"),
        Decimal("500"),
        params,
        Decimal("0.01"),
    )
    assert updated.effective_stop >= state.effective_stop


def test_trailing_stop_would_decrease_stays_flat() -> None:
    state = TrailingStopState(
        entry_price=Decimal("50000"),
        stop_initial=Decimal("48000"),
        highest_close=Decimal("52000"),
        trail_stop=Decimal("49000"),
        effective_stop=Decimal("49000"),
    )
    params = StrategyParameters()
    updated = compute_trailing_stop_update(
        state,
        Decimal("50000"),
        Decimal("2000"),
        params,
        Decimal("0.01"),
    )
    assert updated.effective_stop == state.effective_stop
