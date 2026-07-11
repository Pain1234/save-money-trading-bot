"""Integration tests for position close lifecycle (PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from paper_trading.db.orm import PaperPositionRow
from paper_trading.enums import PaperPositionStatus
from paper_trading.repository import PaperTradingRepository

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.integration.test_postgres_repository import _insert_intent


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


@requires_postgres
def test_closed_position_persists_entry_atr14(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    intent_id = _insert_intent(repo)
    position = repo.create_position(
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
    assert position.entry_atr14 == Decimal("1000")
