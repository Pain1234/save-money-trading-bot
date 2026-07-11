"""Add canonical EXIT fills for stop closes.

Revision ID: 006_exit_fills
Revises: 005_entry_atr14
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_exit_fills"
down_revision: str | None = "005_entry_atr14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_fills",
        sa.Column("fill_kind", sa.String(8), nullable=False, server_default="ENTRY"),
    )
    op.add_column(
        "paper_fills",
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("paper_fills", "paper_order_id", nullable=True)
    op.create_foreign_key(
        "fk_paper_fills_position_id",
        "paper_fills",
        "paper_positions",
        ["position_id"],
        ["position_id"],
    )
    op.create_check_constraint(
        "ck_paper_fills_kind_refs",
        "paper_fills",
        "(fill_kind = 'ENTRY' AND paper_order_id IS NOT NULL AND position_id IS NULL) "
        "OR (fill_kind = 'EXIT' AND position_id IS NOT NULL)",
    )
    op.create_index(
        "uq_paper_fills_exit_position_candle",
        "paper_fills",
        ["position_id", "candle_key", "fill_sequence"],
        unique=True,
        postgresql_where=sa.text("fill_kind = 'EXIT'"),
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM paper_fills WHERE fill_kind = 'EXIT' OR paper_order_id IS NULL")
    )
    op.drop_index("uq_paper_fills_exit_position_candle", table_name="paper_fills")
    op.drop_constraint("ck_paper_fills_kind_refs", "paper_fills", type_="check")
    op.drop_constraint("fk_paper_fills_position_id", "paper_fills", type_="foreignkey")
    op.alter_column("paper_fills", "paper_order_id", nullable=False)
    op.drop_column("paper_fills", "position_id")
    op.drop_column("paper_fills", "fill_kind")
