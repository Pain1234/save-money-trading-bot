"""Tests for scheduled fill lifecycle."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.enums import PaperSide, SignalType, TradeIntentStatus
from paper_trading.execution import EntryExecutionRejected, TransactionalFillResult
from paper_trading.lifecycle import (
    SYMBOL_PROCESSING_ORDER,
    FillProcessingContext,
    process_scheduled_intents_for_open,
)
from paper_trading.models import TradeIntent
from risk_engine.models import RiskParameters
from strategy_engine.models import StrategyParameters

from tests.paper_trading.conftest_execution import DEFAULT_CONSTRAINTS, EXECUTION_CONFIG, utc_dt


def _intent(symbol: str = "BTC") -> TradeIntent:
    return TradeIntent(
        intent_id=uuid4(),
        idempotency_key=f"{symbol}:k",
        symbol=symbol,
        side=PaperSide.LONG,
        signal_type=SignalType.BREAKOUT,
        signal_time=utc_dt(2024, 1, 15),
        scheduled_fill_time=utc_dt(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED,
        strategy_evaluation_id=uuid4(),
        created_at=utc_dt(2024, 1, 15),
        updated_at=utc_dt(2024, 1, 15),
    )


def _ctx(symbol: str = "BTC") -> FillProcessingContext:
    return FillProcessingContext(
        open_ref=Decimal("50000"),
        atr14=Decimal("1000"),
        candle_open_time=utc_dt(2024, 1, 16),
        constraints=DEFAULT_CONSTRAINTS,
        strategy_params=StrategyParameters(),
        risk_params=RiskParameters(),
        execution_config=EXECUTION_CONFIG,
        day_candles={},
        prior_closes={},
        processed_intent_ids=frozenset(),
    )


def test_fill_processing_symbol_order() -> None:
    assert SYMBOL_PROCESSING_ORDER == ("BTC", "ETH", "SOL")


def test_fill_before_delay_skipped() -> None:
    repo = MagicMock()
    fill_service = MagicMock()
    results = process_scheduled_intents_for_open(
        repo,
        fill_service,
        process_time=utc_dt(2024, 1, 16),
        fill_delay_seconds=60,
        symbol_contexts={"BTC": _ctx()},
    )
    assert results[0].processed == 0
    fill_service.execute_scheduled_paper_fill.assert_not_called()


def test_fill_idempotent_via_service() -> None:
    repo = MagicMock()
    intent = _intent()
    repo.get_scheduled_intents_for_symbol.return_value = (intent,)
    repo.update_intent_status.return_value = intent
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)

    fill_service = MagicMock()
    fill_service.execute_scheduled_paper_fill.return_value = TransactionalFillResult(
        created=False,
        fill=None,
        order=None,
        position=None,
        intent=intent,
    )
    results = process_scheduled_intents_for_open(
        repo,
        fill_service,
        process_time=utc_dt(2024, 1, 16, 0, 1, 0),
        fill_delay_seconds=0,
        symbol_contexts={"BTC": _ctx()},
    )
    assert results[0].processed == 1
    assert fill_service.execute_scheduled_paper_fill.call_count == 1


def test_risk_rejection_no_position() -> None:
    repo = MagicMock()
    intent = _intent()
    repo.get_scheduled_intents_for_symbol.return_value = (intent,)
    repo.update_intent_status.return_value = intent
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)

    fill_service = MagicMock()
    fill_service.execute_scheduled_paper_fill.return_value = EntryExecutionRejected(
        reason_codes=("RC_REJECT_LEVERAGE",),
        detail="risk rejected",
    )
    results = process_scheduled_intents_for_open(
        repo,
        fill_service,
        process_time=utc_dt(2024, 1, 16, 0, 1, 0),
        fill_delay_seconds=0,
        symbol_contexts={"BTC": _ctx()},
    )
    assert results[0].rejected == 1
