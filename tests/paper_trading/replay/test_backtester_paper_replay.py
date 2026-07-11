"""Backtester vs paper orchestrator replay parity."""

from __future__ import annotations

import pytest
from backtester.engine import BacktestEngine
from strategy_engine.models import SignalIntentKind

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    backtest_config_for_symbols,
    build_breakout_historical_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_backtester_paper_breakout_entry_parity(e2e_harness: PaperE2EHarness) -> None:
    symbol = "BTC"
    hist = build_breakout_historical_bundle(symbol)
    bt_config = backtest_config_for_symbols((symbol,))
    bt_result = BacktestEngine().run(hist, bt_config)
    assert len(bt_result.trades) == 1
    bt_trade = bt_result.trades[0]

    harness = e2e_harness
    bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
    eval_result = harness.evaluate_at_close(symbol, bundle, eval_time)
    assert eval_result.intent is not None
    fill_candle = candle_at(hist, symbol, 30)
    harness.fill_at_open(
        process_time=fill_candle.open_time,
        symbol_contexts={symbol: fill_context_for_bundle(bundle, eval_time, fill_candle)},
    )
    fills = harness.repo.list_fills(limit=1)
    assert len(fills) == 1
    paper_fill = fills[0]
    assert paper_fill.fill_time == bt_trade.entry_time
    assert paper_fill.fill_price == bt_trade.entry_fill_price
    assert paper_fill.quantity == bt_trade.quantity
    position = harness.repo.list_positions(limit=1)[0]
    assert position.initial_stop == bt_trade.initial_stop


def test_backtester_paper_rejection_parity_no_signal(e2e_harness: PaperE2EHarness) -> None:
    symbol = "BTC"
    hist = build_breakout_historical_bundle(symbol, include_exit_candle=False)
    flat_hist = __import__("backtester.models", fromlist=["HistoricalDataBundle"]).HistoricalDataBundle(
        daily={symbol: hist.daily[symbol][:10]},
        weekly=hist.weekly,
        monthly=hist.monthly,
    )
    bt_result = BacktestEngine().run(flat_hist, backtest_config_for_symbols((symbol,)))
    assert len(bt_result.trades) == 0
    harness = e2e_harness
    bundle, eval_time = historical_to_strategy_bundle(flat_hist, symbol)
    result = harness.evaluate_at_close(symbol, bundle, eval_time)
    entries = [
        e for e in bt_result.strategy_evaluations
        if e.signal_intent.kind == SignalIntentKind.LONG_ENTRY
    ]
    if not entries:
        assert result.intent is None
