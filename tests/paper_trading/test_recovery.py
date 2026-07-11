"""Unit tests for recovery consistency checks."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.config import PaperTradingConfig
from paper_trading.enums import PaperOrderStatus, RuntimeStatus, TradeIntentStatus
from paper_trading.models import PaperOrder, RuntimeState, TradeIntent
from paper_trading.recovery import IssueSeverity, RecoveryService

from tests.paper_trading.conftest_execution import utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _runtime(status: RuntimeStatus = RuntimeStatus.STOPPED) -> RuntimeState:
    now = utc_dt(2024, 1, 16)
    return RuntimeState(
        instance_id=uuid4(),
        status=status,
        heartbeat_at=now,
        version=1,
    )


def test_orphan_scheduler_run_is_auto_repairable() -> None:
    repo = MagicMock()
    repo.get_running_scheduler_runs.return_value = (
        MagicMock(run_id=uuid4(), job_name="daily_signal_evaluation"),
    )
    repo.get_runtime_state.return_value = _runtime()
    repo.list_all_intents.return_value = ()
    repo.list_all_positions.return_value = ()
    repo.list_all_fills.return_value = ()
    repo.count_open_positions_by_symbol.return_value = {}

    service = RecoveryService(repo, _config())
    issues = service.run_consistency_checks()
    assert any(i.code == "orphan_scheduler_run" and i.severity == IssueSeverity.AUTO_REPAIRABLE for i in issues)


def test_multiple_open_positions_is_fatal() -> None:
    repo = MagicMock()
    repo.get_running_scheduler_runs.return_value = ()
    repo.get_runtime_state.return_value = _runtime()
    repo.list_all_intents.return_value = ()
    repo.list_all_positions.return_value = ()
    repo.list_all_fills.return_value = ()
    repo.count_open_positions_by_symbol.return_value = {"BTC": 2}

    service = RecoveryService(repo, _config())
    issues = service.run_consistency_checks()
    fatal = [i for i in issues if i.code == "multiple_open_positions"]
    assert len(fatal) == 1
    assert fatal[0].severity == IssueSeverity.FATAL


def test_open_order_with_fill_auto_repair() -> None:
    repo = MagicMock()
    repo.get_running_scheduler_runs.return_value = ()
    repo.get_runtime_state.return_value = _runtime()
    intent_id = uuid4()
    order_id = uuid4()
    intent = TradeIntent(
        intent_id=intent_id,
        idempotency_key="k",
        symbol="BTC",
        signal_type="BREAKOUT",
        signal_time=utc_dt(2024, 1, 15),
        scheduled_fill_time=utc_dt(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED,
        strategy_evaluation_id=uuid4(),
        created_at=utc_dt(2024, 1, 15),
        updated_at=utc_dt(2024, 1, 15),
    )
    order = PaperOrder(
        paper_order_id=order_id,
        intent_id=intent_id,
        symbol="BTC",
        requested_quantity=Decimal("0.1"),
        remaining_quantity=Decimal("0.1"),
        expected_fill_time=utc_dt(2024, 1, 16),
        status=PaperOrderStatus.OPEN,
        created_at=utc_dt(2024, 1, 15),
        updated_at=utc_dt(2024, 1, 15),
    )
    repo.list_all_intents.return_value = (intent,)
    repo.get_order_for_intent.return_value = order
    repo.get_fills_for_order.return_value = (MagicMock(),)
    repo.list_all_positions.return_value = ()
    repo.list_all_fills.return_value = ()
    repo.count_open_positions_by_symbol.return_value = {}

    service = RecoveryService(repo, _config())
    issues = service.run_consistency_checks()
    repairs = service.apply_auto_repairs(issues)
    assert any(i.code == "open_order_with_fill" for i in issues)
    assert repairs
