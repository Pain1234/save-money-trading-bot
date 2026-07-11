"""Replay idempotency tests."""

from __future__ import annotations

import pytest

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_breakout_historical_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_double_evaluation_produces_single_row(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    first = harness.evaluate_at_close("BTC", bundle, eval_time)
    second = harness.evaluate_at_close("BTC", bundle, eval_time)
    assert first.created is True
    assert second.created is False
    assert first.evaluation.evaluation_id == second.evaluation.evaluation_id
    assert len(harness.repo.list_evaluations(limit=100)) == 1


def test_double_fill_produces_single_fill(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    harness.evaluate_at_close("BTC", bundle, eval_time)
    fill_candle = candle_at(hist, "BTC", 30)
    ctx = fill_context_for_bundle(bundle, eval_time, fill_candle)
    harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts={"BTC": ctx})
    harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts={"BTC": ctx})
    assert len(harness.repo.list_fills(limit=10)) == 1
