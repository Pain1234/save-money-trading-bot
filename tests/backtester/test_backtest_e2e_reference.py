# ruff: noqa: E402
"""End-to-end backtest without mocked Strategy or Risk engines."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from backtester.engine import BacktestEngine
from backtester.execution import compute_fee
from backtester.models import HistoricalDataBundle
from risk_engine.models import RiskParameters
from strategy_engine.models import SignalIntentKind
from strategy_engine.stops import compute_initial_stop

from tests.backtester.conftest import DEFAULT_CONSTRAINTS, dt, make_config
from tests.strategy_engine.conftest import (
    build_flat_daily_series,
    build_rising_monthly_series,
    build_rising_weekly_series,
    make_daily_candle,
)


def _build_breakout_bundle(symbol: str = "BTC") -> HistoricalDataBundle:
    daily_cs = build_flat_daily_series(symbol, 30, start=dt(2024, 1, 1))
    candles = list(daily_cs.candles)
    last = candles[-1]
    candles[-1] = make_daily_candle(
        symbol,
        last.open_time,
        "100",
        "130",
        "99",
        "125",
        vol="2000",
    )
    fill_open = last.open_time + timedelta(days=1)
    candles.append(
        make_daily_candle(symbol, fill_open, "100", "101", "86", "89", vol="1000")
    )
    weekly = build_rising_weekly_series(symbol, 55, start_price=Decimal("100"))
    monthly = build_rising_monthly_series(symbol, 25, start_price=Decimal("100"))
    return HistoricalDataBundle(
        daily={symbol: tuple(candles)},
        weekly={symbol: weekly.candles},
        monthly={symbol: monthly.candles},
    )


def test_e2e_long_entry_fill_stop_reference() -> None:
    symbol = "BTC"
    bundle = _build_breakout_bundle(symbol)
    config = make_config(
        (symbol,),
        initial_cash="100000",
        fee_entry="0.001",
        fee_exit="0.001",
        slippage_bps="0",
        funding_enabled=False,
        risk_params=RiskParameters(risk_per_trade_pct=Decimal("0.005")),
    )

    result = BacktestEngine().run(bundle, config)

    entries = [
        e
        for e in result.strategy_evaluations
        if e.signal_intent.kind == SignalIntentKind.LONG_ENTRY
    ]
    assert len(entries) == 1
    assert len(result.trades) == 1

    trade = result.trades[0]
    assert trade.exit_time is not None
    assert trade.gross_pnl is not None
    assert trade.net_pnl is not None
    assert trade.initial_risk_usd is not None

    fill = trade.entry_fill_price
    tick = DEFAULT_CONSTRAINTS.price_tick_size
    params = config.strategy_params
    atr = entries[0].atr
    assert atr is not None
    expected_stop = compute_initial_stop(fill, atr, params, tick)
    assert trade.initial_stop == expected_stop

    qty = trade.quantity
    entry_fee = compute_fee(fill * qty, config.fee_model.entry_fee_rate)
    exit_fee = compute_fee(trade.exit_fill_price * qty, config.fee_model.exit_fee_rate)
    expected_gross = (trade.exit_fill_price - fill) * qty
    expected_net = expected_gross - entry_fee - exit_fee - trade.funding

    assert trade.gross_pnl == expected_gross
    assert trade.fees == entry_fee + exit_fee
    assert trade.net_pnl == expected_net

    budget = config.initial_cash * config.risk_params.risk_per_trade_pct
    assert trade.initial_risk_usd <= budget

    expected_end = config.initial_cash - entry_fee + expected_gross - exit_fee
    assert result.end_capital == expected_end
    assert result.total_fees == entry_fee + exit_fee
    assert result.total_funding == Decimal("0")

    if trade.initial_risk_usd and trade.initial_risk_usd > 0:
        expected_r = (expected_net / trade.initial_risk_usd).quantize(Decimal("0.001"))
        assert trade.r_multiple == expected_r
