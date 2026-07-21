"""Unit tests for recovery consistency checks."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.clock import FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import PaperFillKind, PaperOrderStatus, RuntimeStatus, TradeIntentStatus
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


def test_independent_accounting_mismatch_is_manual_recovery_issue() -> None:
    repo = MagicMock()
    repo.get_wallet.return_value = MagicMock(
        cash=Decimal("100001"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        total_realized_pnl=Decimal("0"),
    )
    repo.list_positions.return_value = ()
    repo.get_open_positions.return_value = ()
    repo.list_all_fills.return_value = ()

    issue = RecoveryService(repo, _config()).run_accounting_verification()

    assert issue is not None
    assert issue.code == "accounting_reconciliation_mismatch"
    assert issue.severity == IssueSeverity.MANUAL
    assert issue.details == {
        "mismatches": (
            "wallet cash mismatch: db=100001 reconstructed=100000",
        )
    }


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

    service = RecoveryService(repo, _config(), clock=FixedClock(utc_dt(2024, 1, 16)))
    issues = service.run_consistency_checks()
    repairs = service.apply_auto_repairs(issues)
    assert any(i.code == "fill_without_economic_chain" for i in issues)
    assert not any("order_" in r for r in repairs)


def test_open_order_with_fill_auto_repair_when_chain_consistent() -> None:
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
    fill = MagicMock()
    fill.fill_kind = PaperFillKind.ENTRY
    fill.symbol = "BTC"
    fill.quantity = Decimal("0.1")
    fill.fill_price = Decimal("50000")
    position = MagicMock()
    position.entry_intent_id = intent_id
    position.quantity = Decimal("0.1")
    position.average_entry_price = Decimal("50000")
    position.current_stop = Decimal("48000")
    position.initial_stop = Decimal("48000")
    position.highest_close_since_entry = Decimal("50000")
    position.position_id = uuid4()
    repo.list_all_intents.return_value = (intent,)
    repo.get_order_for_intent.return_value = order
    repo.get_fills_for_order.return_value = (fill,)
    repo.session.get.return_value = MagicMock(intent_id=intent_id, status=PaperOrderStatus.OPEN.value)
    repo.get_open_position_for_symbol.return_value = position
    repo.get_wallet.return_value = MagicMock()
    repo.list_all_positions.return_value = (position,)
    repo.list_all_fills.return_value = (fill,)
    repo.count_open_positions_by_symbol.return_value = {}
    repo.list_stop_events_for_position.return_value = ()

    service = RecoveryService(repo, _config(), clock=FixedClock(utc_dt(2024, 1, 16)))
    issues = service.run_consistency_checks()
    repairs = service.apply_auto_repairs(issues)
    assert any(i.code == "open_order_with_fill" for i in issues)
    assert repairs
