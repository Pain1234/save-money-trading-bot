"""Tests for scheduled fill lifecycle."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import PaperSide, RuntimeStatus, SignalType, TradeIntentStatus
from paper_trading.execution import EntryExecutionRejected, TransactionalFillResult
from paper_trading.lifecycle import (
    SYMBOL_PROCESSING_ORDER,
    FillProcessingContext,
    process_scheduled_intents_for_open,
)
from paper_trading.models import RuntimeState, TradeIntent
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


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _ready_runtime() -> RuntimeState:
    return RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=utc_dt(2024, 1, 16),
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
        config=_config(),
        market_data_ready=lambda: True,
    )
    assert results[0].processed == 0
    fill_service.execute_scheduled_paper_fill.assert_not_called()


def test_fill_idempotent_via_service() -> None:
    repo = MagicMock()
    intent = _intent()
    repo.get_runtime_state.return_value = _ready_runtime()
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
        config=_config(),
        market_data_ready=lambda: True,
    )
    assert results[0].processed == 1
    assert fill_service.execute_scheduled_paper_fill.call_count == 1


def test_risk_rejection_no_position() -> None:
    repo = MagicMock()
    intent = _intent()
    repo.get_runtime_state.return_value = _ready_runtime()
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
        config=_config(),
        market_data_ready=lambda: True,
    )
    assert results[0].rejected == 1


@pytest.mark.parametrize(
    ("runtime_update", "expected_reason"),
    [
        ({"paused": True}, "paused"),
        ({"kill_switch": True}, "kill_switch"),
        ({"heartbeat_at": utc_dt(2024, 1, 16) - timedelta(seconds=301)}, "stale_heartbeat"),
        ({"status": RuntimeStatus.DEGRADED}, "runtime_not_ready"),
    ],
)
def test_pending_fill_is_cancelled_when_final_entry_authorization_fails(
    runtime_update: dict[str, object],
    expected_reason: str,
) -> None:
    repo = MagicMock()
    intent = _intent()
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=utc_dt(2024, 1, 16),
    ).model_copy(update=runtime_update)
    repo.get_runtime_state.return_value = runtime
    repo.get_scheduled_intents_for_symbol.return_value = (intent,)
    repo.update_intent_status.return_value = intent.model_copy(
        update={"status": TradeIntentStatus.CANCELLED}
    )
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    fill_service = MagicMock()

    results = process_scheduled_intents_for_open(
        repo,
        fill_service,
        process_time=utc_dt(2024, 1, 16, 0, 1, 0),
        fill_delay_seconds=0,
        symbol_contexts={"BTC": _ctx()},
        config=_config(),
        market_data_ready=lambda: True,
    )

    assert results[0].processed == 1
    assert results[0].skipped == 1
    fill_service.execute_scheduled_paper_fill.assert_not_called()
    assert repo.update_intent_status.call_args.args == (
        intent.intent_id,
        TradeIntentStatus.CANCELLED.value,
    )
    assert expected_reason in repo.update_intent_status.call_args.kwargs[
        "rejection_reason"
    ]["reason_codes"]
