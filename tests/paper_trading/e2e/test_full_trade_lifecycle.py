"""Full deterministic BTC trade lifecycle E2E (PostgreSQL)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from backtester.execution import compute_fee
from paper_trading.enums import PaperPositionStatus, TradeIntentStatus
from strategy_engine.stops import compute_initial_stop

from tests.backtester.conftest import DEFAULT_CONSTRAINTS
from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_extended_lifecycle_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_full_btc_trade_lifecycle(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    symbol = "BTC"
    hist = build_extended_lifecycle_bundle(symbol)
    signal_idx = 29
    fill_idx = 30
    exit_idx = 35

    bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=signal_idx + 1)
    first_eval = harness.evaluate_at_close(symbol, bundle, eval_time)
    assert first_eval.created is True
    assert first_eval.intent is not None
    assert first_eval.intent.status == TradeIntentStatus.SCHEDULED
    assert first_eval.intent.scheduled_fill_time == candle_at(hist, symbol, fill_idx).open_time

    fill_candle = candle_at(hist, symbol, fill_idx)
    fill_time = fill_candle.open_time
    harness.fill_at_open(
        process_time=fill_time,
        symbol_contexts={
            symbol: fill_context_for_bundle(bundle, eval_time, fill_candle),
        },
    )
    position = harness.repo.get_open_position_for_symbol(symbol)
    assert position is not None
    assert position.status == PaperPositionStatus.OPEN
    assert position.quantity > 0
    assert position.entry_atr14 > 0
    assert position.current_stop >= position.initial_stop

    wallet_after_entry = harness.wallet_cash()
    assert wallet_after_entry < Decimal("100000")

    for day_idx in range(fill_idx + 1, exit_idx):
        day = candle_at(hist, symbol, day_idx)
        eval_bundle, day_eval_time = historical_to_strategy_bundle(
            hist, symbol, daily_count=day_idx + 1
        )
        harness.evaluate_at_close(symbol, eval_bundle, day_eval_time)
        harness.update_trailing(
            evaluation_time=day_eval_time,
            daily_candles={symbol: day},
            atr_by_symbol={symbol: position.entry_atr14},
        )
        updated = harness.repo.get_open_position_for_symbol(symbol)
        assert updated is not None
        assert updated.current_stop >= position.current_stop
        position = updated

    exit_candle = candle_at(hist, symbol, exit_idx)
    harness.process_stops(
        process_time=exit_candle.open_time,
        daily_candles={symbol: exit_candle},
    )
    closed = harness.repo.get_open_position_for_symbol(symbol)
    assert closed is None

    counts_after = harness.counts()
    repeat_eval = harness.evaluate_at_close(symbol, bundle, eval_time)
    assert repeat_eval.created is False
    harness.fill_at_open(
        process_time=fill_time,
        symbol_contexts={
            symbol: fill_context_for_bundle(bundle, eval_time, fill_candle),
        },
    )
    counts_repeat = harness.counts()
    assert counts_repeat.evaluations == counts_after.evaluations
    assert counts_repeat.intents == counts_after.intents
    assert counts_repeat.fills == counts_after.fills


def test_entry_fill_price_and_stop_from_actual_fill(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    symbol = "BTC"
    hist = build_extended_lifecycle_bundle(symbol)
    bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
    harness.evaluate_at_close(symbol, bundle, eval_time)
    fill_candle = candle_at(hist, symbol, 30)
    harness.fill_at_open(
        process_time=fill_candle.open_time,
        symbol_contexts={
            symbol: fill_context_for_bundle(bundle, eval_time, fill_candle),
        },
    )
    fills = harness.repo.list_fills(limit=10)
    assert len(fills) == 1
    fill = fills[0]
    position = harness.repo.get_position(
        harness.repo.list_positions(limit=1)[0].position_id
    )
    assert position is not None
    expected_stop = compute_initial_stop(
        fill.fill_price,
        position.entry_atr14,
        harness.strategy_params,
        DEFAULT_CONSTRAINTS.price_tick_size,
    )
    assert position.initial_stop == expected_stop
    fee = compute_fee(fill.fill_price * fill.quantity, Decimal("0.0005"))
    assert fill.fee == fee
