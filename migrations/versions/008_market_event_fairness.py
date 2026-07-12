"""Persistent market event group fairness state.

Revision ID: 008_market_event_fairness
Revises: 007_scheduler_recovery
Create Date: 2026-07-12
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_market_event_fairness"
down_revision: str | None = "007_scheduler_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FAIRNESS_CURSOR_SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


def upgrade() -> None:
    op.create_table(
        "market_event_fairness_cursor",
        sa.Column("cursor_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_rotation_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "group_rotation_cursor >= 0",
            name="ck_market_event_fairness_cursor_nonnegative",
        ),
    )
    op.create_table(
        "market_event_group_state",
        sa.Column("group_key", sa.String(128), primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("group_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("defer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("defer_count >= 0", name="ck_market_event_group_defer_count"),
    )
    op.create_index(
        "ix_market_event_group_state_next_attempt",
        "market_event_group_state",
        ["next_attempt_at"],
    )
    op.execute(
        sa.text(
            "INSERT INTO market_event_fairness_cursor (cursor_id, group_rotation_cursor) "
            "VALUES (:id, 0)"
        ).bindparams(id=FAIRNESS_CURSOR_SINGLETON_ID)
    )


def downgrade() -> None:
    op.drop_index("ix_market_event_group_state_next_attempt", table_name="market_event_group_state")
    op.drop_table("market_event_group_state")
    op.drop_table("market_event_fairness_cursor")
