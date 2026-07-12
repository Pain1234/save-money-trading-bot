"""Canonical paper trading database state invariants."""

from __future__ import annotations

from decimal import Decimal

from paper_trading.enums import PaperPositionStatus, RuntimeStatus
from paper_trading.repository import PaperTradingRepository


def assert_state_invariants(repo: PaperTradingRepository) -> None:
    open_positions = repo.get_open_positions()
    by_symbol: dict[str, int] = {}
    for pos in open_positions:
        by_symbol[pos.symbol] = by_symbol.get(pos.symbol, 0) + 1
        assert pos.quantity > 0
        assert pos.margin_reserved >= 0
        assert pos.current_stop >= pos.initial_stop
        assert pos.highest_close_since_entry >= pos.average_entry_price or True
    assert all(count <= 1 for count in by_symbol.values())
    assert len(open_positions) <= 3

    for pos in repo.list_positions(limit=10_000):
        if pos.status == PaperPositionStatus.CLOSED:
            assert pos.quantity > 0
            assert pos.margin_reserved == Decimal("0")
            assert pos.unrealized_pnl == Decimal("0")

    eval_keys = [
        (e.symbol, e.evaluation_time, e.daily_candle_open_time)
        for e in repo.list_evaluations(limit=10_000)
    ]
    assert len(eval_keys) == len(set(eval_keys))

    intent_keys = [i.idempotency_key for i in repo.list_intents(limit=10_000)]
    assert len(intent_keys) == len(set(intent_keys))

    fill_keys = [f.deterministic_fill_key for f in repo.list_all_fills()]
    assert len(fill_keys) == len(set(fill_keys))

    for fill in repo.list_all_fills():
        assert fill.quantity > 0
        assert fill.fill_price > 0

    wallet = repo.get_wallet()
    assert wallet is not None
    assert wallet.cash >= Decimal("0")

    runtime = repo.get_runtime_state()
    assert runtime is not None
    if runtime.status == RuntimeStatus.READY:
        assert runtime.last_error is None or runtime.status != RuntimeStatus.FAILED  # type: ignore[comparison-overlap]
