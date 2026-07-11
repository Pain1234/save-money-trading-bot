# ruff: noqa: E402
"""Intent lifecycle regression tests."""

from __future__ import annotations

from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine
from backtester.intent import build_client_intent_id
from risk_engine.models import RiskParameters
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import EntryType, ReasonCode

from tests.backtester.conftest import (
    dt,
    flat_daily_series,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
)


@patch("backtester.engine.StrategyEngine.evaluate")
def test_rejected_intent_has_reject_reason_not_approved(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 3)
    config = make_config((symbol,), risk_params=RiskParameters(max_open_positions=0))

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.risk_rejections) >= 1
    rej = result.risk_rejections[0]
    assert ReasonCode.RC_RISK_APPROVED not in rej.reason_codes


@patch("backtester.engine.StrategyEngine.evaluate")
def test_filled_intent_in_processed_ids(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "110", "99", "105"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.processed_intent_ids) == 1
    assert len(result.open_positions) == 1


@patch("backtester.engine.StrategyEngine.evaluate")
def test_duplicate_intent_blocked(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 4)
    eval_t = evaluation_time_for_daily(daily[0])
    intent_id = build_client_intent_id(symbol, STRATEGY_VERSION, eval_t, EntryType.BREAKOUT)
    config = make_config((symbol,), initial_processed=(intent_id,))

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == eval_t:
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.trades) == 0
    assert intent_id in result.processed_intent_ids


@patch("backtester.engine.StrategyEngine.evaluate")
def test_rejection_never_only_approved_code(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 3)
    config = make_config((symbol,), risk_params=RiskParameters(max_open_positions=0))

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    for rej in result.risk_rejections:
        assert rej.reason_codes != (ReasonCode.RC_RISK_APPROVED,)
