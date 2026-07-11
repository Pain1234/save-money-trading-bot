"""Crash boundary tests at transaction edges."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_breakout_historical_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)
from tests.paper_trading.integration.test_postgres_repository import _insert_intent

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_crash_after_wallet_update_rolls_back(e2e_harness: PaperE2EHarness) -> None:
    repo = e2e_harness.repo
    wallet = repo.get_wallet()
    assert wallet is not None
    nested = repo.session.begin_nested()
    repo.update_wallet(cash_delta=Decimal("-100"))
    nested.rollback()
    after = repo.get_wallet()
    assert after is not None
    assert after.cash == wallet.cash


def test_crash_after_intent_insert_rolls_back(e2e_harness: PaperE2EHarness) -> None:
    repo = e2e_harness.repo
    intent_id = uuid4()
    nested = repo.session.begin_nested()
    _insert_intent(repo, intent_id=intent_id)
    nested.rollback()
    assert repo.get_intent(intent_id) is None


def test_partial_fill_flow_commits_atomically(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    harness.evaluate_at_close("BTC", bundle, eval_time)
    fill_candle = candle_at(hist, "BTC", 30)
    ctx = fill_context_for_bundle(bundle, eval_time, fill_candle)
    harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts={"BTC": ctx})
    assert len(harness.repo.list_fills(limit=5)) == 1
    assert harness.repo.get_open_position_for_symbol("BTC") is not None
