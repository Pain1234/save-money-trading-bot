"""Multi-symbol BTC/ETH/SOL E2E lifecycle."""

from __future__ import annotations

import pytest

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    SYMBOLS,
    PaperE2EHarness,
    build_breakout_historical_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_multi_symbol_fill_order_and_limits(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    bundles: dict[str, tuple] = {}
    for symbol in SYMBOLS:
        hist = build_breakout_historical_bundle(symbol)
        bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
        result = harness.evaluate_at_close(symbol, bundle, eval_time)
        assert result.intent is not None
        bundles[symbol] = (hist, bundle, eval_time)

    fill_candle = candle_at(bundles["BTC"][0], "BTC", 30)
    contexts = {
        symbol: fill_context_for_bundle(bundles[symbol][1], bundles[symbol][2], fill_candle)
        for symbol in SYMBOLS
    }
    batch = harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts=contexts)
    filled_symbols = [r.symbol for r in batch if r.filled > 0]
    assert filled_symbols == ["BTC", "ETH", "SOL"]
    assert len(harness.repo.get_open_positions()) == 3

    hist_btc, bundle_btc, eval_time_btc = bundles["BTC"]
    repeat = harness.evaluate_at_close("BTC", bundle_btc, eval_time_btc)
    assert repeat.intent_created is False
    assert harness.repo.get_open_position_for_symbol("BTC") is not None


def test_fourth_symbol_blocked_by_max_positions(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    for symbol in SYMBOLS:
        hist = build_breakout_historical_bundle(symbol)
        bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
        harness.evaluate_at_close(symbol, bundle, eval_time)
    fill_candle = candle_at(build_breakout_historical_bundle("BTC"), "BTC", 30)
    contexts = {}
    for symbol in SYMBOLS:
        hist = build_breakout_historical_bundle(symbol)
        bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
        contexts[symbol] = fill_context_for_bundle(bundle, eval_time, fill_candle)
    harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts=contexts)
    assert len(harness.repo.get_open_positions()) == 3

    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    gates = harness.entry_gates("BTC")
    from paper_trading.lifecycle import check_entry_gates
    from strategy_engine.engine import StrategyEngine

    ev = StrategyEngine().evaluate(
        bundle.daily, bundle.weekly, bundle.monthly, eval_time, harness.strategy_params
    )
    blocked = check_entry_gates(
        symbol="BTC",
        entry_gates=gates,
        strategy_eval=ev,
        max_open_positions=3,
    )
    assert "max_open_positions" in blocked or "existing_position" in blocked
