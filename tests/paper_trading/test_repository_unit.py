"""Offline repository unit tests (mappers and row builders)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from paper_trading.db.orm import StrategyEvaluationRow, TradeIntentRow
from paper_trading.enums import SignalType, TradeIntentStatus
from paper_trading.ids import trade_intent_key
from paper_trading.mappers import evaluation_row_to_domain, intent_row_to_domain


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def test_evaluation_mapper_roundtrip_decimal() -> None:
    row = StrategyEvaluationRow(
        evaluation_id=uuid4(),
        symbol="BTC",
        evaluation_time=_utc(2024, 1, 15),
        daily_candle_open_time=_utc(2024, 1, 15),
        weekly_candle_key=_utc(2024, 1, 8),
        monthly_candle_key=_utc(2024, 1, 1),
        daily_candle_key=_utc(2024, 1, 15),
        strategy_version="1.0",
        regime_result={"ok": True},
        entry_result={"signal": "LONG"},
        rejection_reasons=[],
        deterministic_input_hash="abc",
        created_at=_utc(2024, 1, 15),
    )
    domain = evaluation_row_to_domain(row)
    assert domain.symbol == "BTC"


def test_intent_mapper_uses_decimal_fields() -> None:
    eval_id = uuid4()
    signal_time = datetime(2024, 1, 15, 0, 0, 5, tzinfo=UTC)
    row = TradeIntentRow(
        intent_id=uuid4(),
        idempotency_key=trade_intent_key("BTC", "1.0", signal_time, SignalType.BREAKOUT),
        symbol="BTC",
        side="LONG",
        signal_type="BREAKOUT",
        signal_time=signal_time,
        scheduled_fill_time=_utc(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED.value,
        strategy_evaluation_id=eval_id,
        created_at=signal_time,
        updated_at=signal_time,
    )
    domain = intent_row_to_domain(row)
    assert isinstance(domain.requested_entry, Decimal)
    assert domain.requested_entry == Decimal("50000")
