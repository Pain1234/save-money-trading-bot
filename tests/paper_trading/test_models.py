"""Tests for paper trading domain model invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from paper_trading.enums import (
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionStatus,
    PaperSide,
    RuntimeStatus,
    SignalType,
    TradeIntentStatus,
)
from paper_trading.models import (
    PaperFill,
    PaperOrder,
    PaperPosition,
    PaperWalletState,
    PositionStopEvent,
    RuntimeState,
    TradeIntent,
)


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def test_runtime_state_decimal_fields_not_float() -> None:
    wallet = PaperWalletState(
        wallet_id=uuid4(),
        cash=Decimal("100000"),
        updated_at=_utc(2024, 1, 1),
    )
    assert isinstance(wallet.cash, Decimal)
    assert not isinstance(wallet.cash, float)


def test_paper_fill_requires_positive_quantity() -> None:
    with pytest.raises(ValueError, match="> 0"):
        PaperFill(
            fill_id=uuid4(),
            paper_order_id=uuid4(),
            symbol="BTC",
            side=PaperSide.LONG,
            quantity=Decimal("0"),
            market_open_price=Decimal("50000"),
            slippage=Decimal("25"),
            fill_price=Decimal("50025"),
            fee=Decimal("25"),
            fill_time=_utc(2024, 1, 16),
            candle_key=_utc(2024, 1, 16),
            deterministic_fill_key="k",
        )


def test_paper_position_stop_below_entry() -> None:
    with pytest.raises(ValueError, match="below average_entry_price"):
        PaperPosition(
            position_id=uuid4(),
            symbol="BTC",
            status=PaperPositionStatus.OPEN,
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000"),
            initial_stop=Decimal("51000"),
            current_stop=Decimal("51000"),
            highest_close_since_entry=Decimal("50000"),
            entry_atr14=Decimal("1000"),
            margin_reserved=Decimal("2500"),
            entry_intent_id=uuid4(),
            opened_at=_utc(2024, 1, 16),
        )


def test_paper_position_current_stop_monotonic() -> None:
    with pytest.raises(ValueError, match="current_stop"):
        PaperPosition(
            position_id=uuid4(),
            symbol="BTC",
            status=PaperPositionStatus.OPEN,
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000"),
            initial_stop=Decimal("48000"),
            current_stop=Decimal("47000"),
            highest_close_since_entry=Decimal("50000"),
            entry_atr14=Decimal("1000"),
            margin_reserved=Decimal("2500"),
            entry_intent_id=uuid4(),
            opened_at=_utc(2024, 1, 16),
        )


def test_closed_position_requires_closed_at() -> None:
    with pytest.raises(ValueError, match="closed_at"):
        PaperPosition(
            position_id=uuid4(),
            symbol="BTC",
            status=PaperPositionStatus.CLOSED,
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000"),
            initial_stop=Decimal("48000"),
            current_stop=Decimal("48000"),
            highest_close_since_entry=Decimal("50000"),
            entry_atr14=Decimal("1000"),
            margin_reserved=Decimal("0"),
            entry_intent_id=uuid4(),
            opened_at=_utc(2024, 1, 16),
            realized_pnl=Decimal("100"),
        )


def test_stop_event_rejects_decreasing_stop() -> None:
    with pytest.raises(ValueError, match="new_stop"):
        PositionStopEvent(
            stop_event_id=uuid4(),
            position_id=uuid4(),
            previous_stop=Decimal("48000"),
            new_stop=Decimal("47000"),
            highest_close=Decimal("52000"),
            atr=Decimal("1000"),
            evaluation_time=_utc(2024, 1, 17),
            reason="trailing",
        )


def test_trade_intent_valid() -> None:
    now = _utc(2024, 1, 15)
    intent = TradeIntent(
        intent_id=uuid4(),
        idempotency_key="BTC:1.0:2024-01-15T00:00:05Z:BREAKOUT",
        symbol="BTC",
        side=PaperSide.LONG,
        signal_type=SignalType.BREAKOUT,
        signal_time=now,
        scheduled_fill_time=_utc(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED,
        strategy_evaluation_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    assert intent.status == TradeIntentStatus.SCHEDULED


def test_paper_order_remaining_non_negative() -> None:
    with pytest.raises(ValueError, match="remaining_quantity"):
        PaperOrder(
            paper_order_id=uuid4(),
            intent_id=uuid4(),
            symbol="BTC",
            side=PaperSide.LONG,
            order_type=PaperOrderType.MARKET_AT_OPEN,
            requested_quantity=Decimal("1"),
            remaining_quantity=Decimal("-0.1"),
            expected_fill_time=_utc(2024, 1, 16),
            status=PaperOrderStatus.OPEN,
            created_at=_utc(2024, 1, 15),
            updated_at=_utc(2024, 1, 15),
        )


def test_runtime_state_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RuntimeState(
            instance_id=uuid4(),
            status=RuntimeStatus.STOPPED,
            heartbeat_at=datetime(2024, 1, 1),
        )
