"""PostgreSQL repository integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from paper_trading.db.orm import (
    PaperPositionRow,
    StrategyEvaluationRow,
    TradeIntentRow,
)
from paper_trading.enums import PaperPositionStatus, SignalType, TradeIntentStatus
from paper_trading.ids import paper_fill_key, trade_intent_key
from paper_trading.repository import PaperTradingRepository
from sqlalchemy.exc import IntegrityError

from tests.paper_trading.conftest import requires_postgres


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def _evaluation_row(symbol: str = "BTC", daily: datetime | None = None) -> StrategyEvaluationRow:
    daily = daily or _utc(2024, 1, 15)
    return StrategyEvaluationRow(
        evaluation_id=uuid4(),
        symbol=symbol,
        evaluation_time=daily,
        daily_candle_open_time=daily,
        weekly_candle_key=_utc(2024, 1, 8),
        monthly_candle_key=_utc(2024, 1, 1),
        daily_candle_key=daily,
        strategy_version="1.0",
        regime_result={"long": True},
        entry_result={"type": "BREAKOUT"},
        rejection_reasons=[],
        deterministic_input_hash="hash1",
        created_at=daily,
    )


@requires_postgres
def test_decimal_roundtrip(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    wallet = repo.get_wallet()
    assert wallet is not None
    assert isinstance(wallet.cash, Decimal)
    assert wallet.cash == Decimal("100000")


@requires_postgres
def test_duplicate_evaluation_insert(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    row = _evaluation_row()
    first, created1 = repo.insert_or_get_strategy_evaluation(row)
    second, created2 = repo.insert_or_get_strategy_evaluation(_evaluation_row())
    assert created1 is True
    assert created2 is False
    assert first.evaluation_id == second.evaluation_id


@requires_postgres
def test_duplicate_intent_insert(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    eval_row = _evaluation_row()
    signal_time = datetime(2024, 1, 15, 0, 0, 5, tzinfo=UTC)
    evaluation, _ = repo.insert_or_get_strategy_evaluation(eval_row)
    intent_row = TradeIntentRow(
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
        strategy_evaluation_id=evaluation.evaluation_id,
        created_at=signal_time,
        updated_at=signal_time,
    )
    first, c1 = repo.insert_or_get_trade_intent(intent_row)
    duplicate = TradeIntentRow(
        intent_id=uuid4(),
        idempotency_key="different-key",
        symbol="BTC",
        side="LONG",
        signal_type="BREAKOUT",
        signal_time=signal_time,
        scheduled_fill_time=_utc(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED.value,
        strategy_evaluation_id=evaluation.evaluation_id,
        created_at=signal_time,
        updated_at=signal_time,
    )
    second, c2 = repo.insert_or_get_trade_intent(duplicate)
    assert c1 is True
    assert c2 is False
    assert first.intent_id == second.intent_id


@requires_postgres
def test_duplicate_fill_insert(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    eval_row = _evaluation_row(daily=_utc(2024, 2, 1))
    signal_time = datetime(2024, 2, 1, 0, 0, 5, tzinfo=UTC)
    candle_key = _utc(2024, 2, 2)
    evaluation, _ = repo.insert_or_get_strategy_evaluation(eval_row)
    intent_row = TradeIntentRow(
        intent_id=uuid4(),
        idempotency_key=trade_intent_key("BTC", "1.0", signal_time, SignalType.BREAKOUT),
        symbol="BTC",
        side="LONG",
        signal_type="BREAKOUT",
        signal_time=signal_time,
        scheduled_fill_time=candle_key,
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED.value,
        strategy_evaluation_id=evaluation.evaluation_id,
        created_at=signal_time,
        updated_at=signal_time,
    )
    intent, _ = repo.insert_or_get_trade_intent(intent_row)
    order_row = repo.new_order_row(
        intent_id=intent.intent_id,
        symbol="BTC",
        side="LONG",
        order_type="MARKET_AT_OPEN",
        requested_quantity=Decimal("0.1"),
        remaining_quantity=Decimal("0"),
        expected_fill_time=candle_key,
        status="FILLED",
        created_at=signal_time,
        updated_at=signal_time,
    )
    order, _ = repo.insert_or_get_paper_order(order_row)
    fill_key = paper_fill_key(order.paper_order_id, candle_key, 0)
    fill_row = repo.new_fill_row(
        paper_order_id=order.paper_order_id,
        symbol="BTC",
        side="LONG",
        quantity=Decimal("0.1"),
        market_open_price=Decimal("50000"),
        slippage=Decimal("25"),
        fill_price=Decimal("50025"),
        fee=Decimal("2.5"),
        fill_time=candle_key,
        candle_key=candle_key,
        fill_sequence=0,
        deterministic_fill_key=fill_key,
    )
    first, c1 = repo.insert_or_get_paper_fill(fill_row)
    second, c2 = repo.insert_or_get_paper_fill(
        repo.new_fill_row(
            paper_order_id=order.paper_order_id,
            symbol="BTC",
            side="LONG",
            quantity=Decimal("0.1"),
            market_open_price=Decimal("50000"),
            slippage=Decimal("25"),
            fill_price=Decimal("50025"),
            fee=Decimal("2.5"),
            fill_time=candle_key,
            candle_key=candle_key,
            fill_sequence=0,
            deterministic_fill_key="other-key-should-not-insert",
        )
    )
    assert c1 is True
    assert c2 is False
    assert first.fill_id == second.fill_id


def _insert_intent(
    repo: PaperTradingRepository,
    *,
    intent_id: UUID | None = None,
    symbol: str = "BTC",
    signal_type: SignalType = SignalType.BREAKOUT,
    daily: datetime | None = None,
) -> UUID:
    daily = daily or _utc(2024, 1, 15)
    eval_row = _evaluation_row(symbol=symbol, daily=daily)
    evaluation, _ = repo.insert_or_get_strategy_evaluation(eval_row)
    intent_id = intent_id or uuid4()
    signal_time = daily.replace(hour=0, minute=0, second=5)
    intent_row = TradeIntentRow(
        intent_id=intent_id,
        idempotency_key=trade_intent_key(symbol, "1.0", signal_time, signal_type),
        symbol=symbol,
        side="LONG",
        signal_type=signal_type.value,
        signal_time=signal_time,
        scheduled_fill_time=_utc(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED.value,
        strategy_evaluation_id=evaluation.evaluation_id,
        created_at=signal_time,
        updated_at=signal_time,
    )
    repo.insert_or_get_trade_intent(intent_row)
    return intent_id


@requires_postgres
def test_second_open_position_same_symbol_rejected(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    intent_id = _insert_intent(repo)
    second_intent_id = _insert_intent(
        repo,
        signal_type=SignalType.PULLBACK,
        daily=_utc(2024, 1, 16),
    )
    repo.create_position(
            PaperPositionRow(
                position_id=uuid4(),
                symbol="BTC",
                status=PaperPositionStatus.OPEN.value,
                quantity=Decimal("0.1"),
                average_entry_price=Decimal("50000"),
                initial_stop=Decimal("48000"),
                current_stop=Decimal("48000"),
                highest_close_since_entry=Decimal("50000"),
                entry_atr14=Decimal("1000"),
                margin_reserved=Decimal("2500"),
                entry_intent_id=intent_id,
                opened_at=_utc(2024, 1, 16),
        )
    )
    with pytest.raises(IntegrityError):
        repo.create_position(
            PaperPositionRow(
                position_id=uuid4(),
                symbol="BTC",
                status=PaperPositionStatus.OPEN.value,
                quantity=Decimal("0.2"),
                average_entry_price=Decimal("51000"),
                initial_stop=Decimal("49000"),
                current_stop=Decimal("49000"),
                highest_close_since_entry=Decimal("51000"),
                entry_atr14=Decimal("1000"),
                margin_reserved=Decimal("5100"),
                entry_intent_id=second_intent_id,
                opened_at=_utc(2024, 1, 17),
            )
        )
        db_session.flush()


@requires_postgres
def test_open_positions_different_symbols_allowed(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    btc_intent = _insert_intent(repo, symbol="BTC")
    eth_intent = _insert_intent(repo, symbol="ETH")
    repo.create_position(
            PaperPositionRow(
                position_id=uuid4(),
                symbol="BTC",
                status=PaperPositionStatus.OPEN.value,
                quantity=Decimal("0.1"),
                average_entry_price=Decimal("50000"),
                initial_stop=Decimal("48000"),
                current_stop=Decimal("48000"),
                highest_close_since_entry=Decimal("50000"),
                entry_atr14=Decimal("1000"),
                margin_reserved=Decimal("2500"),
                entry_intent_id=btc_intent,
                opened_at=_utc(2024, 1, 16),
            )
        )
    repo.create_position(
        PaperPositionRow(
            position_id=uuid4(),
            symbol="ETH",
            status=PaperPositionStatus.OPEN.value,
            quantity=Decimal("1"),
            average_entry_price=Decimal("3000"),
            initial_stop=Decimal("2800"),
            current_stop=Decimal("2800"),
            highest_close_since_entry=Decimal("3000"),
            entry_atr14=Decimal("100"),
            margin_reserved=Decimal("1500"),
            entry_intent_id=eth_intent,
            opened_at=_utc(2024, 1, 16),
        )
    )
    open_positions = repo.get_open_positions()
    assert len(open_positions) == 2


@requires_postgres
def test_transaction_rollback(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    wallet_before = repo.get_wallet()
    assert wallet_before is not None
    nested = db_session.begin_nested()
    repo.update_wallet(cash_delta=Decimal("-1000"))
    repo.append_audit_event(
        event_type="TEST_ROLLBACK",
        aggregate_type="wallet",
        aggregate_id=wallet_before.wallet_id,
        payload_json={"delta": "-1000"},
    )
    nested.rollback()
    wallet_after = repo.get_wallet()
    assert wallet_after is not None
    assert wallet_after.cash == wallet_before.cash
    assert wallet_after.version == wallet_before.version


def _position_row(
    *,
    symbol: str,
    status: PaperPositionStatus,
    intent_id: UUID,
    opened_at: datetime,
    quantity: str = "0.1",
) -> PaperPositionRow:
    return PaperPositionRow(
        position_id=uuid4(),
        symbol=symbol,
        status=status.value,
        quantity=Decimal(quantity),
        average_entry_price=Decimal("50000"),
        initial_stop=Decimal("48000"),
        current_stop=Decimal("48000"),
        highest_close_since_entry=Decimal("50000"),
        entry_atr14=Decimal("1000"),
        margin_reserved=Decimal("2500"),
        entry_intent_id=intent_id,
        opened_at=opened_at,
        closed_at=opened_at if status == PaperPositionStatus.CLOSED else None,
    )


@requires_postgres
def test_list_positions_open_only_and_cursor(db_session) -> None:
    """open_only includes OPEN+CLOSING, excludes CLOSED; cursor pagination works."""
    repo = PaperTradingRepository(db_session)
    open_intent = _insert_intent(repo, symbol="BTC", daily=_utc(2024, 3, 1))
    closing_intent = _insert_intent(repo, symbol="ETH", daily=_utc(2024, 3, 2))
    closed_intent = _insert_intent(repo, symbol="SOL", daily=_utc(2024, 3, 3))

    open_row = _position_row(
        symbol="BTC",
        status=PaperPositionStatus.OPEN,
        intent_id=open_intent,
        opened_at=_utc(2024, 3, 10),
    )
    closing_row = _position_row(
        symbol="ETH",
        status=PaperPositionStatus.CLOSING,
        intent_id=closing_intent,
        opened_at=_utc(2024, 3, 11),
    )
    closed_row = _position_row(
        symbol="SOL",
        status=PaperPositionStatus.CLOSED,
        intent_id=closed_intent,
        opened_at=_utc(2024, 3, 12),
    )
    repo.create_position(open_row)
    repo.create_position(closing_row)
    repo.create_position(closed_row)
    db_session.flush()

    open_only = repo.list_positions(limit=50, open_only=True)
    statuses = {p.status for p in open_only}
    symbols = {p.symbol for p in open_only}
    assert PaperPositionStatus.OPEN in statuses
    assert PaperPositionStatus.CLOSING in statuses
    assert PaperPositionStatus.CLOSED not in statuses
    assert symbols == {"BTC", "ETH"}
    assert all(p.position_id != closed_row.position_id for p in open_only)

    closed_only = repo.list_positions(limit=50, status=PaperPositionStatus.CLOSED.value)
    assert len(closed_only) == 1
    assert closed_only[0].position_id == closed_row.position_id

    # Cursor: newest open_only first (opened_at desc) → ETH then BTC
    page1 = repo.list_positions(limit=1, open_only=True)
    assert len(page1) == 1
    assert page1[0].symbol == "ETH"
    page2 = repo.list_positions(
        limit=1,
        open_only=True,
        after_opened_at=page1[0].opened_at,
        after_position_id=page1[0].position_id,
    )
    assert len(page2) == 1
    assert page2[0].symbol == "BTC"
    page3 = repo.list_positions(
        limit=1,
        open_only=True,
        after_opened_at=page2[0].opened_at,
        after_position_id=page2[0].position_id,
    )
    assert page3 == ()
