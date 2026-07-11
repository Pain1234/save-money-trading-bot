# ruff: noqa: E402
"""Look-ahead regression tests for open-fill marks."""

from __future__ import annotations

from decimal import Decimal

from backtester.portfolio import resolve_marks_at_open

from tests.backtester.conftest import dt, make_daily


def _position(symbol: str, entry: str = "100"):
    from backtester.models import SimulatedPosition

    return SimulatedPosition(
        symbol=symbol,
        quantity=Decimal("1"),
        entry_price=Decimal(entry),
        entry_time=dt(2024, 1, 1),
        initial_stop=Decimal("90"),
        trail_stop=Decimal("90"),
        effective_stop=Decimal("90"),
        highest_close=Decimal(entry),
        entry_atr14=Decimal("2"),
        client_intent_id="x",
        margin_reserved=Decimal("50"),
    )


def test_resolve_marks_uses_open_not_same_day_close() -> None:
    btc = make_daily("BTC", dt(2024, 1, 2), "90", "150", "85", "140")
    eth = make_daily("ETH", dt(2024, 1, 2), "50", "55", "49", "54")
    day_candles = {"BTC": btc, "ETH": eth}
    prior = {"BTC": Decimal("100")}

    marks = resolve_marks_at_open((_position("BTC"),), day_candles, prior)

    assert marks["BTC"] == Decimal("90")
    assert marks["BTC"] != btc.close


def test_resolve_marks_falls_back_to_prior_close() -> None:
    eth = make_daily("ETH", dt(2024, 1, 2), "50", "55", "49", "54")
    prior = {"BTC": Decimal("100")}

    marks = resolve_marks_at_open((_position("BTC"),), {"ETH": eth}, prior)

    assert marks["BTC"] == Decimal("100")


def test_same_day_close_would_inflate_equity() -> None:
    pos = _position("BTC", "100")
    btc = make_daily("BTC", dt(2024, 1, 2), "90", "150", "85", "140")
    wallet = Decimal("100000")

    mark_open = resolve_marks_at_open((pos,), {"BTC": btc}, {})["BTC"]
    mark_close_wrong = btc.close

    equity_open = wallet + pos.quantity * (mark_open - pos.entry_price)
    equity_close_bug = wallet + pos.quantity * (mark_close_wrong - pos.entry_price)

    assert equity_close_bug - equity_open == Decimal("50")
