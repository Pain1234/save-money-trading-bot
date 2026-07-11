"""ORM metadata tests (offline)."""

from __future__ import annotations

from paper_trading.db.base import Base
from paper_trading.db.orm import PaperFillRow, PaperPositionRow, PaperWalletRow
from sqlalchemy import REAL, Float


def test_all_tables_registered() -> None:
    names = set(Base.metadata.tables.keys())
    expected = {
        "runtime_state",
        "strategy_evaluations",
        "trade_intents",
        "paper_orders",
        "paper_fills",
        "paper_positions",
        "position_stop_history",
        "portfolio_snapshots",
        "funding_events",
        "audit_events",
        "scheduler_runs",
        "paper_wallet",
    }
    assert expected.issubset(names)


def test_no_float_columns() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, (Float, REAL)), (
                f"{table.name}.{column.name} uses float type"
            )


def test_money_columns_use_numeric() -> None:
    fill_qty = PaperFillRow.__table__.c.quantity.type
    assert fill_qty.precision == 38
    assert fill_qty.scale == 18

    wallet_cash = PaperWalletRow.__table__.c.cash.type
    assert wallet_cash.precision == 38


def test_partial_unique_index_on_open_positions() -> None:
    table = PaperPositionRow.__table__
    index_names = {idx.name for idx in table.indexes}
    assert "uq_paper_positions_open_symbol" in index_names
