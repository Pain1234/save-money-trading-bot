# ruff: noqa: E402
"""Regression tests for perpetual margin accounting."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine
from backtester.execution import compute_fee
from backtester.portfolio import (
    compute_equity,
    compute_unrealized_pnl,
    position_margin,
)
from risk_engine.models import RiskParameters

from tests.backtester.conftest import (
    dt,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
)


def _signal_day0(mock_eval, symbol: str, daily, *, stop: str = "95", atr: str = "2") -> None:
    from backtester.data import evaluation_time_for_daily

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop=stop, atr=atr)
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect


@patch("backtester.engine.StrategyEngine.evaluate")
def test_entry_wallet_only_deducts_fee(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "101", "99", "100"),
    )
    config = make_config(
        (symbol,),
        initial_cash="100000",
        slippage_bps="0",
        fee_entry="0.001",
        fee_exit="0",
    )
    _signal_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)

    assert len(result.open_positions) == 1
    pos = result.open_positions[0]
    entry_fee = compute_fee(pos.entry_price * pos.quantity, Decimal("0.001"))
    assert result.equity_curve[-1].cash == config.initial_cash - entry_fee
    expected_margin = position_margin(
        pos.entry_price * pos.quantity, config.risk_params.max_leverage
    )
    assert pos.margin_reserved == expected_margin
    assert result.equity_curve[-1].cash > config.initial_cash - pos.entry_price * pos.quantity


@patch("backtester.engine.StrategyEngine.evaluate")
def test_equity_unchanged_without_price_move(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "101", "99", "100"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0.001", fee_exit="0")
    _signal_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    entry_fee = result.total_fees
    last = result.equity_curve[-1]
    assert last.equity == config.initial_cash - entry_fee
    assert last.unrealized_pnl == Decimal("0")


def test_unrealized_pnl_on_rise() -> None:
    from backtester.models import SimulatedPosition

    pos = SimulatedPosition(
        symbol="BTC",
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_time=dt(2024, 1, 1),
        initial_stop=Decimal("90"),
        trail_stop=Decimal("90"),
        effective_stop=Decimal("90"),
        highest_close=Decimal("100"),
        entry_atr14=Decimal("2"),
        client_intent_id="x",
        margin_reserved=Decimal("50"),
    )
    marks = {"BTC": Decimal("110")}
    assert compute_unrealized_pnl((pos,), marks) == Decimal("10")
    assert compute_equity(Decimal("1000"), (pos,), marks) == Decimal("1010")


def test_unrealized_pnl_on_decline() -> None:
    from backtester.models import SimulatedPosition

    pos = SimulatedPosition(
        symbol="BTC",
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        entry_time=dt(2024, 1, 1),
        initial_stop=Decimal("90"),
        trail_stop=Decimal("90"),
        effective_stop=Decimal("90"),
        highest_close=Decimal("100"),
        entry_atr14=Decimal("2"),
        client_intent_id="x",
        margin_reserved=Decimal("100"),
    )
    marks = {"BTC": Decimal("90")}
    assert compute_unrealized_pnl((pos,), marks) == Decimal("-20")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_exit_at_entry_price_net_of_fees_and_funding(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "107", "96", "106.75"),
        make_daily(symbol, dt(2024, 1, 4), "100", "100", "100", "100"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0.001", fee_exit="0.001")
    _signal_day0(mock_eval, symbol, daily, stop="95")
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.gross_pnl == Decimal("0")
    assert result.end_capital == config.initial_cash - result.total_fees - result.total_funding


@patch("backtester.engine.StrategyEngine.evaluate")
def test_winning_trade_wallet_includes_gross_minus_fees(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "104", "130", "103", "120"),
        make_daily(symbol, dt(2024, 1, 4), "120", "125", "119", "122"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")
    _signal_day0(mock_eval, symbol, daily, stop="50")
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.open_positions) == 1
    assert result.end_capital > config.initial_cash


@patch("backtester.engine.StrategyEngine.evaluate")
def test_losing_trade_reduces_wallet(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "101", "88", "89"),
    )
    config = make_config((symbol,), slippage_bps="0", fee_entry="0.001", fee_exit="0.001")
    _signal_day0(mock_eval, symbol, daily, stop="95")
    result = BacktestEngine().run(make_bundle(symbol, daily=daily), config)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.gross_pnl is not None and trade.gross_pnl < 0
    assert result.end_capital < config.initial_cash - result.total_fees


@patch("backtester.engine.StrategyEngine.evaluate")
def test_two_positions_at_2x_leverage(mock_eval) -> None:
    symbols = ("BTC", "ETH")
    d0, d1, d2 = dt(2024, 1, 1), dt(2024, 1, 2), dt(2024, 1, 3)
    daily = {
        "BTC": (
            make_daily("BTC", d0, "100", "101", "99", "100"),
            make_daily("BTC", d1, "100", "101", "99", "100"),
            make_daily("BTC", d2, "100", "101", "99", "100"),
        ),
        "ETH": (
            make_daily("ETH", d0, "50", "51", "49", "50"),
            make_daily("ETH", d1, "50", "51", "49", "50"),
            make_daily("ETH", d2, "50", "51", "49", "50"),
        ),
    }
    from backtester.models import HistoricalDataBundle

    bundle = HistoricalDataBundle(
        daily=daily,
        weekly={"BTC": (), "ETH": ()},
        monthly={"BTC": (), "ETH": ()},
    )
    risk = RiskParameters(max_leverage=Decimal("2"))
    config = make_config(
        symbols, risk_params=risk, slippage_bps="0", fee_entry="0", fee_exit="0"
    )

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily["BTC"][0]):
            return make_long_entry_eval(
                daily_s.symbol, eval_time, stop="90" if daily_s.symbol == "BTC" else "45"
            )
        return make_no_entry_eval(daily_s.symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.open_positions) == 2
    total_margin = sum(p.margin_reserved for p in result.open_positions)
    assert total_margin > Decimal("0")
    assert result.equity_curve[-1].cash == config.initial_cash
