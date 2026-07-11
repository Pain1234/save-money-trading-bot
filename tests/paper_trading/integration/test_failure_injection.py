"""Failure injection tests with PostgreSQL transactions."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from paper_trading.repository import PaperTradingRepository

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.integration.test_postgres_repository import _evaluation_row, _insert_intent


@requires_postgres
def test_transaction_rollback_after_wallet_update(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    wallet_before = repo.get_wallet()
    assert wallet_before is not None
    nested = db_session.begin_nested()
    repo.update_wallet(cash_delta=Decimal("-500"))
    nested.rollback()
    wallet_after = repo.get_wallet()
    assert wallet_after is not None
    assert wallet_after.cash == wallet_before.cash


@requires_postgres
def test_crash_after_intent_insert_rolls_back(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    intent_id = uuid4()
    nested = db_session.begin_nested()
    _insert_intent(repo, intent_id=intent_id)
    nested.rollback()
    assert repo.get_intent(intent_id) is None


@requires_postgres
def test_audit_and_domain_mutation_rollback_together(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    wallet = repo.get_wallet()
    assert wallet is not None
    nested = db_session.begin_nested()
    repo.update_wallet(cash_delta=Decimal("-100"))
    repo.append_audit_event(
        event_type="TEST_INJECTION",
        aggregate_type="wallet",
        aggregate_id=wallet.wallet_id,
        payload_json={"test": True},
    )
    nested.rollback()
    wallet_after = repo.get_wallet()
    assert wallet_after is not None
    assert wallet_after.cash == wallet.cash
    events = repo.list_audit_events(limit=5)
    assert all(e.event_type != "TEST_INJECTION" for e in events)


@requires_postgres
def test_evaluation_insert_survives_outer_transaction(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    evaluation, created = repo.insert_or_get_strategy_evaluation(_evaluation_row())
    assert created is True
    assert evaluation.symbol == "BTC"
