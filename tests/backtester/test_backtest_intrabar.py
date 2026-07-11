# ruff: noqa: E402
"""Intrabar ordering regression tests."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine
from backtester.models import ExitReason

from tests.backtester.conftest import (
    dt,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
)


@patch("backtester.engine.StrategyEngine.evaluate")
def test_same_candle_low_triggers_initial_stop(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "88", "89"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    trade = result.trades[0]
    assert trade.exit_time == dt(2024, 1, 2)
    assert trade.exit_reason in (ExitReason.STOP_INITIAL, ExitReason.STOP_TRAILING)


@patch("backtester.engine.StrategyEngine.evaluate")
def test_same_candle_high_does_not_raise_trail_before_eod(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "200", "96", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "101", "99", "100"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.open_positions) == 1
    pos = result.open_positions[0]
    assert pos.highest_close == Decimal("100")
    assert pos.trail_stop <= pos.initial_stop
