"""Accounting adapter tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from paper_trading.accounting import compute_paper_equity, paper_position_to_simulated
from paper_trading.enums import PaperPositionStatus
from paper_trading.models import PaperPosition, PaperWalletState

from tests.paper_trading.conftest_execution import utc_dt


def test_paper_equity_matches_backtester_semantics() -> None:
    wallet = PaperWalletState(
        wallet_id=uuid4(),
        cash=Decimal("100000"),
        updated_at=utc_dt(2024, 1, 16),
    )
    position = PaperPosition(
        position_id=uuid4(),
        symbol="BTC",
        status=PaperPositionStatus.OPEN,
        quantity=Decimal("0.1"),
        average_entry_price=Decimal("50000"),
        initial_stop=Decimal("48000"),
        current_stop=Decimal("48000"),
        highest_close_since_entry=Decimal("50000"),
        entry_atr14=Decimal("1000"),
        margin_reserved=Decimal("2500"),
        entry_intent_id=uuid4(),
        opened_at=utc_dt(2024, 1, 16),
    )
    marks = {"BTC": Decimal("51000")}
    equity = compute_paper_equity(wallet, (position,), marks)
    assert equity == Decimal("100100")
    simulated = paper_position_to_simulated(position)
    assert simulated.quantity == Decimal("0.1")
