# ruff: noqa: E402
"""Fill-based risk regression tests."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine
from risk_engine.models import RiskParameters

from tests.backtester.conftest import (
    dt,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
)


def _run_gap_scenario(*, open_price: str, close_signal: str):
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), close_signal, "101", "99", close_signal),
        make_daily(symbol, dt(2024, 1, 2), open_price, "105", "80", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "110", "99", "105"),
    )
    config = make_config(
        (symbol,),
        slippage_bps="0",
        fee_entry="0",
        fee_exit="0",
        risk_params=RiskParameters(risk_per_trade_pct=Decimal("0.005")),
    )

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="90", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    with patch("backtester.engine.StrategyEngine.evaluate", side_effect=side_effect):
        result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)

    trade = result.trades[0] if result.trades else None
    return result, trade


@patch("backtester.engine.StrategyEngine.evaluate")
def test_gap_down_actual_risk_within_budget(mock_eval) -> None:
    result, trade = _run_gap_scenario(open_price="98", close_signal="100")
    assert trade is not None
    assert trade.initial_risk_usd is not None
    budget = result.config.initial_cash * Decimal("0.005")
    assert trade.initial_risk_usd <= budget


@patch("backtester.engine.StrategyEngine.evaluate")
def test_gap_down_fill_risk_capped(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "98", "105", "80", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "110", "99", "105"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="90", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    trade = result.trades[0] if result.trades else None
    assert trade is not None
    budget = config.initial_cash * Decimal("0.005")
    assert trade.initial_risk_usd <= budget


@patch("backtester.engine.StrategyEngine.evaluate")
def test_fill_stop_matches_position_stop(mock_eval) -> None:
    result, trade = _run_gap_scenario(open_price="102", close_signal="100")
    assert trade is not None
    pos = next((p for p in result.open_positions if p.symbol == "BTC"), None)
    if pos:
        assert trade.initial_stop == pos.initial_stop


@patch("backtester.engine.StrategyEngine.evaluate")
def test_gap_up_conservative_sizing(mock_eval) -> None:
    result, trade = _run_gap_scenario(open_price="105", close_signal="100")
    assert trade is not None
    budget = result.config.initial_cash * Decimal("0.005")
    assert trade.initial_risk_usd <= budget
