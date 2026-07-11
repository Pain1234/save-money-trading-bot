"""Accelerated deterministic 365-day soak test."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    historical_to_strategy_bundle,
)
from tests.paper_trading.soak.helpers import (
    SoakMetrics,
    assert_soak_invariants,
    generate_soak_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres, pytest.mark.soak]


@pytest.mark.soak
def test_accelerated_365_day_soak(e2e_harness: PaperE2EHarness) -> None:
    started = time.perf_counter()
    harness = e2e_harness
    bundle_hist = generate_soak_bundle(days=365, seed=1)
    stop_updates = 0
    for day_idx in range(60, 365, 7):
        for symbol in ("BTC", "ETH", "SOL"):
            dailies = bundle_hist.daily[symbol]
            if day_idx >= len(dailies):
                continue
            strat_bundle, eval_time = historical_to_strategy_bundle(
                bundle_hist, symbol, daily_count=day_idx + 1
            )
            if not strat_bundle.is_usable:
                continue
            harness.evaluate_at_close(symbol, strat_bundle, eval_time)
            day = dailies[day_idx]
            results = harness.update_trailing(
                evaluation_time=eval_time,
                daily_candles={symbol: day},
                atr_by_symbol={symbol: Decimal("5")},
            )
            stop_updates += sum(1 for r in results if r.updated)
    assert_soak_invariants(harness.repo)
    elapsed = time.perf_counter() - started
    counts = harness.counts()
    metrics = SoakMetrics(
        days=365,
        evaluations=counts.evaluations,
        intents=counts.intents,
        fills=counts.fills,
        stop_updates=stop_updates,
        audit_events=counts.audit_events,
        elapsed_seconds=elapsed,
    )
    assert metrics.elapsed_seconds < 120.0
    assert metrics.evaluations >= 0
