"""Tests for deterministic idempotency keys."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from backtester.intent import build_client_intent_id
from paper_trading.enums import SignalType
from paper_trading.ids import (
    deterministic_input_hash,
    funding_event_key,
    paper_fill_key,
    scheduler_run_key,
    stop_update_key,
    strategy_evaluation_key,
    trade_intent_key,
)
from strategy_engine.models import EntryType


def _utc(y: int, m: int, d: int, h: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, second, tzinfo=UTC)


def test_strategy_evaluation_key_stable() -> None:
    t = _utc(2024, 1, 15)
    a = strategy_evaluation_key("1.0", "BTC", t)
    b = strategy_evaluation_key("1.0", "BTC", t)
    assert a == b
    assert a == "1.0:BTC:2024-01-15T00:00:00Z"


def test_strategy_evaluation_key_differs_by_candle() -> None:
    a = strategy_evaluation_key("1.0", "BTC", _utc(2024, 1, 15))
    b = strategy_evaluation_key("1.0", "BTC", _utc(2024, 1, 16))
    assert a != b


def test_trade_intent_key_matches_backtester() -> None:
    signal_time = _utc(2024, 1, 15, 0, 0, 5)
    expected = build_client_intent_id("BTC", "1.0", signal_time, EntryType.BREAKOUT)
    actual = trade_intent_key("BTC", "1.0", signal_time, SignalType.BREAKOUT)
    assert actual == expected


def test_timezone_normalized_to_utc() -> None:
    offset = timezone(timedelta(hours=2))
    local = datetime(2024, 1, 15, 2, 0, 5, tzinfo=offset)
    utc_key = trade_intent_key("BTC", "1.0", local, SignalType.BREAKOUT)
    direct = trade_intent_key("BTC", "1.0", _utc(2024, 1, 15, 0, 0, 5), SignalType.BREAKOUT)
    assert utc_key == direct


def test_naive_datetime_rejected() -> None:
    naive = datetime(2024, 1, 15, 0, 0, 5)
    with pytest.raises(ValueError, match="timezone-aware"):
        trade_intent_key("BTC", "1.0", naive, SignalType.BREAKOUT)


def test_paper_fill_key_includes_sequence() -> None:
    order_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    t = _utc(2024, 1, 16)
    assert paper_fill_key(order_id, t, 0) != paper_fill_key(order_id, t, 1)


def test_funding_and_scheduler_keys() -> None:
    pos_id = UUID("11111111-1111-1111-1111-111111111111")
    t = _utc(2024, 1, 15, 8)
    assert funding_event_key(pos_id, t).startswith(str(pos_id))
    assert scheduler_run_key("daily_eval", t) == "daily_eval:2024-01-15T08:00:00Z"


def test_stop_update_key() -> None:
    pos_id = UUID("22222222-2222-2222-2222-222222222222")
    t = _utc(2024, 1, 15, 0, 0, 5)
    assert stop_update_key(pos_id, t) == f"{pos_id}:2024-01-15T00:00:05Z"


def test_deterministic_input_hash_order_independent() -> None:
    a = {"symbol": "BTC", "price": Decimal("100.5"), "time": _utc(2024, 1, 1)}
    b = {"time": _utc(2024, 1, 1), "price": Decimal("100.5"), "symbol": "BTC"}
    assert deterministic_input_hash(a) == deterministic_input_hash(b)


def test_deterministic_input_hash_changes_with_value() -> None:
    base = {"symbol": "BTC", "price": Decimal("100")}
    changed = {"symbol": "BTC", "price": Decimal("101")}
    assert deterministic_input_hash(base) != deterministic_input_hash(changed)
