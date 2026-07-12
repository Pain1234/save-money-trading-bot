"""Persist soak run identity for scheduler evidence scoping.

Revision ID: 009_soak_run_identity
Revises: 008_market_event_fairness
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_soak_run_identity"
down_revision: str | None = "008_market_event_fairness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "soak_runs",
        sa.Column("soak_run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "scheduler_runs",
        sa.Column("soak_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_scheduler_runs_soak_run_id",
        "scheduler_runs",
        "soak_runs",
        ["soak_run_id"],
        ["soak_run_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_scheduler_runs_soak_run_id",
        "scheduler_runs",
        ["soak_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduler_runs_soak_run_id", table_name="scheduler_runs")
    op.drop_constraint("fk_scheduler_runs_soak_run_id", "scheduler_runs", type_="foreignkey")
    op.drop_column("scheduler_runs", "soak_run_id")
    op.drop_table("soak_runs")
