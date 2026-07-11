"""Add entry_atr14 to paper_positions and snapshot idempotency key.

Revision ID: 005_entry_atr14
Revises: 004_seed
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_entry_atr14"
down_revision: str | None = "004_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUMERIC_MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    op.add_column(
        "paper_positions",
        sa.Column("entry_atr14", NUMERIC_MONEY, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE paper_positions SET entry_atr14 = average_entry_price "
            "WHERE entry_atr14 IS NULL"
        )
    )
    op.alter_column("paper_positions", "entry_atr14", nullable=False)
    op.create_check_constraint(
        "ck_paper_positions_entry_atr_positive",
        "paper_positions",
        "entry_atr14 > 0",
    )

    op.add_column(
        "portfolio_snapshots",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE portfolio_snapshots SET idempotency_key = "
            "'legacy:' || snapshot_id::text WHERE idempotency_key IS NULL"
        )
    )
    op.alter_column("portfolio_snapshots", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_portfolio_snapshots_idempotency",
        "portfolio_snapshots",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_portfolio_snapshots_idempotency", "portfolio_snapshots", type_="unique")
    op.drop_column("portfolio_snapshots", "idempotency_key")
    op.drop_constraint("ck_paper_positions_entry_atr_positive", "paper_positions", type_="check")
    op.drop_column("paper_positions", "entry_atr14")
