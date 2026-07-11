"""Seed runtime_state and paper_wallet singleton rows.

Revision ID: 004_seed
Revises: 003_indexes
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "004_seed"
down_revision: str | None = "003_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_SINGLETON_ID = UUID("00000000-0000-0000-0000-000000000001")
WALLET_SINGLETON_ID = UUID("00000000-0000-0000-0000-000000000002")
DEFAULT_INITIAL_EQUITY = Decimal("100000")


def upgrade() -> None:
    now = datetime.now(tz=UTC)
    op.execute(
        sa.text(
            """
            INSERT INTO runtime_state (
                instance_id, status, heartbeat_at, kill_switch, paused, version
            ) VALUES (
                :instance_id, 'STOPPED', :heartbeat_at, false, false, 1
            )
            ON CONFLICT (instance_id) DO NOTHING
            """
        ).bindparams(instance_id=RUNTIME_SINGLETON_ID, heartbeat_at=now)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO paper_wallet (
                wallet_id, cash, total_realized_pnl, total_fees,
                total_funding, total_slippage, version, updated_at
            ) VALUES (
                :wallet_id, :cash, 0, 0, 0, 0, 1, :updated_at
            )
            ON CONFLICT (wallet_id) DO NOTHING
            """
        ).bindparams(
            wallet_id=WALLET_SINGLETON_ID,
            cash=DEFAULT_INITIAL_EQUITY,
            updated_at=now,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM paper_wallet WHERE wallet_id = :wallet_id").bindparams(
            wallet_id=WALLET_SINGLETON_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM runtime_state WHERE instance_id = :instance_id").bindparams(
            instance_id=RUNTIME_SINGLETON_ID
        )
    )
