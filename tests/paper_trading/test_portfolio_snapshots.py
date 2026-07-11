"""Tests for portfolio snapshots."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.models import PaperWalletState
from paper_trading.portfolio import PortfolioSnapshotService, portfolio_snapshot_key

from tests.paper_trading.conftest_execution import utc_dt


def test_snapshot_idempotency_key_format() -> None:
    key = portfolio_snapshot_key("fill", utc_dt(2024, 1, 16))
    assert key.startswith("portfolio:fill:")


def test_duplicate_snapshot_no_double_write() -> None:
    repo = MagicMock()
    wallet = PaperWalletState(
        wallet_id=uuid4(),
        cash=Decimal("100000"),
        updated_at=utc_dt(2024, 1, 16),
    )
    repo.get_wallet.return_value = wallet
    repo.get_open_positions.return_value = ()
    repo.insert_or_get_portfolio_snapshot.return_value = (MagicMock(), False)
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)

    service = PortfolioSnapshotService(repo)
    _, created = service.capture_snapshot(
        evaluation_time=utc_dt(2024, 1, 16),
        event="fill",
    )
    assert created is False
    repo.append_audit_event.assert_not_called()
