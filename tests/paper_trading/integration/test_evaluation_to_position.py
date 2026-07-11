"""Integration tests for evaluation through position open (PostgreSQL)."""

from __future__ import annotations

from tests.paper_trading.conftest import requires_postgres


@requires_postgres
def test_evaluation_persisted_in_database(db_session) -> None:
    """Smoke test: migrated database accepts strategy evaluation rows."""
    from paper_trading.repository import PaperTradingRepository
    from tests.paper_trading.integration.test_postgres_repository import _evaluation_row

    repo = PaperTradingRepository(db_session)
    with db_session.begin():
        evaluation, created = repo.insert_or_get_strategy_evaluation(_evaluation_row())
    assert created is True
    assert evaluation.symbol == "BTC"
