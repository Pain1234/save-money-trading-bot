"""Funding semantics and gross/net identity (#164)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine
from backtester.models import FundingEvent, FundingModel
from research.metrics_contract import compute_gross_pnl

from tests.backtester.conftest import (
    dt,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
)


def _signal_on_day0(mock_eval, symbol: str, daily) -> None:
    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect


def test_gross_net_funding_identity_regression() -> None:
    """Net -10, fees 2, slippage 3, funding 5 → gross 0."""
    gross = compute_gross_pnl(
        net_pnl=Decimal("-10"),
        fees=Decimal("2"),
        slippage_costs=Decimal("3"),
        funding_costs=Decimal("5"),
    )
    assert gross == Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_assumed_rate_applied_without_bundle_events(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily, funding=())
    config = make_config(
        (symbol,), funding_enabled=True, slippage_bps="0", fee_entry="0", fee_exit="0"
    )
    config = config.model_copy(
        update={"funding_model": FundingModel(enabled=True, assumed_rate=Decimal("0.001"))}
    )
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.total_funding > Decimal("0")
    assert result.funding_enabled is True


@patch("backtester.engine.StrategyEngine.evaluate")
def test_assumed_rate_ignores_bundle_events(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    huge = (
        FundingEvent(timestamp=dt(2024, 1, 2, 12), funding_rate=Decimal("0.5")),
    )
    bundle = make_bundle(symbol, daily=daily, funding=huge)
    config = make_config(
        (symbol,), funding_enabled=True, slippage_bps="0", fee_entry="0", fee_exit="0"
    )
    config = config.model_copy(
        update={"funding_model": FundingModel(enabled=True, assumed_rate=Decimal("0.001"))}
    )
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    # Assumed rate path must not apply the 50% event rate
    assert result.total_funding < Decimal("1000")
    assert result.total_funding > Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_funding_disabled_zero_costs(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
    )
    funding = (
        FundingEvent(timestamp=dt(2024, 1, 2, 12), funding_rate=Decimal("0.01")),
    )
    bundle = make_bundle(symbol, daily=daily, funding=funding)
    config = make_config((symbol,), funding_enabled=False)
    mock_eval.return_value = make_no_entry_eval(
        symbol, evaluation_time_for_daily(daily[0])
    )
    result = BacktestEngine().run(bundle, config)
    assert result.total_funding == Decimal("0")
    assert result.funding_enabled is False


@patch("backtester.engine.StrategyEngine.evaluate")
def test_negative_assumed_rate_credits_position(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily, funding=())
    config = make_config(
        (symbol,), funding_enabled=True, slippage_bps="0", fee_entry="0", fee_exit="0"
    )
    config = config.model_copy(
        update={"funding_model": FundingModel(enabled=True, assumed_rate=Decimal("-0.001"))}
    )
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.total_funding < Decimal("0")
