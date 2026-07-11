"""Portfolio snapshot computation and persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from risk_engine.models import RiskParameters
from strategy_engine.models import Candle

from paper_trading.accounting import (
    compute_paper_equity,
    compute_paper_margin_used,
    compute_paper_open_risk,
    compute_paper_unrealized_pnl,
    resolve_marks_for_paper_positions,
)
from paper_trading.db.orm import PortfolioSnapshotRow
from paper_trading.models import PaperPosition, PaperWalletState, PortfolioSnapshot
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import _transaction_scope


def portfolio_snapshot_key(event: str, evaluation_time: datetime) -> str:
    ts = evaluation_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"portfolio:{event}:{ts}"


class PortfolioSnapshotService:
    """Create idempotent portfolio snapshots."""

    def __init__(self, repository: PaperTradingRepository) -> None:
        self._repo = repository

    def capture_snapshot(
        self,
        *,
        evaluation_time: datetime,
        event: str,
        wallet: PaperWalletState | None = None,
        open_positions: tuple[PaperPosition, ...] | None = None,
        day_candles: dict[str, Candle] | None = None,
        prior_closes: dict[str, Decimal] | None = None,
        risk_params: RiskParameters | None = None,
        cycle_id: UUID | None = None,
    ) -> tuple[PortfolioSnapshot, bool]:
        wallet = wallet or self._repo.get_wallet()
        if wallet is None:
            raise LookupError("paper_wallet not seeded")
        open_positions = (
            open_positions if open_positions is not None else self._repo.get_open_positions()
        )
        day_candles = day_candles or {}
        prior_closes = prior_closes or {}
        marks = resolve_marks_for_paper_positions(open_positions, day_candles, prior_closes)
        unrealized = compute_paper_unrealized_pnl(open_positions, marks)
        equity = compute_paper_equity(wallet, open_positions, marks)
        margin_used = compute_paper_margin_used(open_positions)
        open_risk = compute_paper_open_risk(open_positions, marks)

        key = portfolio_snapshot_key(event, evaluation_time)
        row = PortfolioSnapshotRow(
            snapshot_id=uuid4(),
            evaluation_time=evaluation_time,
            cash=wallet.cash,
            margin_used=margin_used,
            equity=equity,
            unrealized_pnl=unrealized,
            realized_pnl=wallet.total_realized_pnl,
            total_open_risk=open_risk,
            open_position_count=len(open_positions),
            idempotency_key=key,
        )
        with _transaction_scope(self._repo.session):
            snapshot, created = self._repo.insert_or_get_portfolio_snapshot(row)
            if created:
                self._repo.append_audit_event(
                    event_type="PORTFOLIO_SNAPSHOT",
                    aggregate_type="portfolio_snapshot",
                    aggregate_id=snapshot.snapshot_id,
                    payload_json={"event": event, "equity": str(equity)},
                    cycle_id=cycle_id,
                    created_at=evaluation_time,
                )
        return snapshot, created
