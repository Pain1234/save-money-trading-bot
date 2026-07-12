"""Add immutable recovery linkage columns to scheduler_runs.

Revision ID: 007_scheduler_recovery
Revises: 006_exit_fills
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_scheduler_recovery"
down_revision: str | None = "006_exit_fills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduler_runs",
        sa.Column("recovery_of_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "scheduler_runs",
        sa.Column("resolved_by_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_scheduler_runs_recovery_of",
        "scheduler_runs",
        "scheduler_runs",
        ["recovery_of_run_id"],
        ["run_id"],
    )
    op.create_foreign_key(
        "fk_scheduler_runs_resolved_by",
        "scheduler_runs",
        "scheduler_runs",
        ["resolved_by_run_id"],
        ["run_id"],
    )
    op.create_index(
        "ix_scheduler_runs_recovery_of",
        "scheduler_runs",
        ["recovery_of_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduler_runs_recovery_of", table_name="scheduler_runs")
    op.drop_constraint("fk_scheduler_runs_resolved_by", "scheduler_runs", type_="foreignkey")
    op.drop_constraint("fk_scheduler_runs_recovery_of", "scheduler_runs", type_="foreignkey")
    op.drop_column("scheduler_runs", "resolved_by_run_id")
    op.drop_column("scheduler_runs", "recovery_of_run_id")
