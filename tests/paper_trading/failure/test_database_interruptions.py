"""Database interruption and connection semantics."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.paper_trading.conftest import requires_postgres

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_database_reconnect_select_one(migrated_engine) -> None:
    with migrated_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


def test_session_survives_after_flush(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    wallet = repo.get_wallet()
    assert wallet is not None
    db_session.flush()
    again = repo.get_wallet()
    assert again is not None
    assert again.cash == wallet.cash
