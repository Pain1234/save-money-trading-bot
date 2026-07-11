"""Backtest metrics tests."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from backtester.metrics import compute_drawdown_curve, compute_metrics
from backtester.models import BacktestTrade, EquitySnapshot, ExitReason
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import EntryType, ReasonCode

from tests.backtester.conftest import dt


def _trade(net: str, symbol: str = "BTC", r: str | None = None) -> BacktestTrade:
    return BacktestTrade(
        symbol=symbol,
        client_intent_id="id",
        strategy_version=STRATEGY_VERSION,
        entry_type=EntryType.BREAKOUT,
        strategy_reason_codes=(ReasonCode.RC_ENTRY_BREAKOUT_20D,),
        risk_reason_codes=(ReasonCode.RC_RISK_APPROVED,),
        signal_time=dt(2024, 1, 1),
        order_time=dt(2024, 1, 1),
        entry_time=dt(2024, 1, 2),
        entry_reference_price=Decimal("100"),
        entry_fill_price=Decimal("100"),
        quantity=Decimal("1"),
        initial_stop=Decimal("90"),
        exit_time=dt(2024, 1, 5),
        exit_reason=ExitReason.STOP_INITIAL,
        exit_reference_price=Decimal("95"),
        exit_fill_price=Decimal("95"),
        gross_pnl=Decimal(net),
        net_pnl=Decimal(net),
        initial_risk_usd=Decimal("10"),
        r_multiple=Decimal(r) if r else None,
    )


def test_drawdown_curve() -> None:
    curve = (
        EquitySnapshot(time=dt(2024, 1, 1), cash=Decimal("100"), equity=Decimal("100"), unrealized_pnl=Decimal("0"), open_positions=0),
        EquitySnapshot(time=dt(2024, 1, 2), cash=Decimal("100"), equity=Decimal("110"), unrealized_pnl=Decimal("10"), open_positions=1),
        EquitySnapshot(time=dt(2024, 1, 3), cash=Decimal("100"), equity=Decimal("99"), unrealized_pnl=Decimal("-1"), open_positions=1),
    )
    dd = compute_drawdown_curve(curve)
    assert dd[-1].drawdown_pct == Decimal("0.1")


def test_profit_factor() -> None:
    trades = (_trade("100"), _trade("-50"))
    metrics = compute_metrics(
        trades=trades,
        equity_curve=(),
        start_capital=Decimal("10000"),
        end_capital=Decimal("10050"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=dt(2024, 1, 1),
        data_end=dt(2024, 12, 31),
    )
    assert metrics.profit_factor == Decimal("2")


def test_expectancy() -> None:
    trades = (_trade("100"), _trade("-50"))
    metrics = compute_metrics(
        trades=trades,
        equity_curve=(),
        start_capital=Decimal("10000"),
        end_capital=Decimal("10050"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=None,
        data_end=None,
    )
    assert metrics.expectancy_usd == Decimal("25")


def test_cagr() -> None:
    trades = (_trade("1000"),)
    start = dt(2024, 1, 1)
    end = start + timedelta(days=365)
    metrics = compute_metrics(
        trades=trades,
        equity_curve=(),
        start_capital=Decimal("10000"),
        end_capital=Decimal("11000"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=start,
        data_end=end,
    )
    assert metrics.cagr_pct is not None
    assert metrics.cagr_pct > Decimal("0")


def test_sharpe_null_variance() -> None:
    curve = tuple(
        EquitySnapshot(
            time=dt(2024, 1, 1) + timedelta(days=i),
            cash=Decimal("100"),
            equity=Decimal("100"),
            unrealized_pnl=Decimal("0"),
            open_positions=0,
        )
        for i in range(5)
    )
    metrics = compute_metrics(
        trades=(),
        equity_curve=curve,
        start_capital=Decimal("100"),
        end_capital=Decimal("100"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=dt(2024, 1, 1),
        data_end=dt(2024, 1, 5),
    )
    assert metrics.sharpe_ratio is None


def test_sortino_null_variance() -> None:
    curve = tuple(
        EquitySnapshot(
            time=dt(2024, 1, 1) + timedelta(days=i),
            cash=Decimal("100"),
            equity=Decimal("100"),
            unrealized_pnl=Decimal("0"),
            open_positions=0,
        )
        for i in range(5)
    )
    metrics = compute_metrics(
        trades=(),
        equity_curve=curve,
        start_capital=Decimal("100"),
        end_capital=Decimal("100"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=dt(2024, 1, 1),
        data_end=dt(2024, 1, 5),
    )
    assert metrics.sortino_ratio is None


def test_no_trades_metrics() -> None:
    metrics = compute_metrics(
        trades=(),
        equity_curve=(),
        start_capital=Decimal("10000"),
        end_capital=Decimal("10000"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=dt(2024, 1, 1),
        data_end=dt(2024, 1, 2),
    )
    assert metrics.trade_count == 0
    assert metrics.win_rate is None
    assert metrics.profit_factor is None


def test_all_winners() -> None:
    trades = (_trade("10"), _trade("20"))
    metrics = compute_metrics(
        trades=trades,
        equity_curve=(),
        start_capital=Decimal("100"),
        end_capital=Decimal("130"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=None,
        data_end=None,
    )
    assert metrics.win_rate == Decimal("1")
    assert metrics.profit_factor is None


def test_all_losers() -> None:
    trades = (_trade("-10"), _trade("-20"))
    metrics = compute_metrics(
        trades=trades,
        equity_curve=(),
        start_capital=Decimal("100"),
        end_capital=Decimal("70"),
        total_fees=Decimal("0"),
        total_funding=Decimal("0"),
        total_slippage=Decimal("0"),
        data_start=None,
        data_end=None,
    )
    assert metrics.win_rate == Decimal("0")
    assert metrics.profit_factor == Decimal("0")
