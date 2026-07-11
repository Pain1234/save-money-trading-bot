"""Multi-symbol cumulative portfolio risk at daily open."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from paper_trading.enums import TradeIntentStatus
from risk_engine.models import RiskParameters

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


def test_third_symbol_rejected_by_portfolio_risk_limit(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    harness.risk_params = RiskParameters(
        risk_per_trade_pct=Decimal("0.005"),
        max_portfolio_risk_pct=Decimal("0.012"),
        max_leverage=Decimal("2"),
    )
    bundles: dict[str, tuple] = {}
    for symbol in SYMBOLS:
        hist = build_breakout_historical_bundle(symbol)
        bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
        result = harness.evaluate_at_close(symbol, bundle, eval_time)
        assert result.intent is not None
        bundles[symbol] = (hist, bundle, eval_time)

    fill_candle = candle_at(bundles["BTC"][0], "BTC", 30)
    contexts = {}
    for symbol in SYMBOLS:
        hist, bundle, eval_time = bundles[symbol]
        ctx = fill_context_for_bundle(bundle, eval_time, fill_candle)
        contexts[symbol] = replace(ctx, risk_params=harness.risk_params)

    batch = harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts=contexts)
    filled = [r.symbol for r in batch if r.filled > 0]
    rejected = [r.symbol for r in batch if r.rejected > 0]
    assert filled[:2] == ["BTC", "ETH"]
    assert "SOL" in rejected
    assert len(harness.repo.get_open_positions()) == 2

    sol_intents = [
        i for i in harness.repo.list_intents(limit=100) if i.symbol == "SOL"
    ]
    assert sol_intents
    assert sol_intents[0].status == TradeIntentStatus.REJECTED

    repeat = harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts=contexts)
    assert sum(r.filled for r in repeat) == 0
    assert len(harness.repo.get_open_positions()) == 2
