"""Allow multiple raw fetch observations per content hash (#80).

Revision ID: 011_raw_fetch_obs
Revises: 010_market_data_datasets
Create Date: 2026-07-15

Irreversible: duplicate content_hash rows cannot restore UNIQUE(content_hash).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "011_raw_fetch_obs"
down_revision: str | None = "010_market_data_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "market_data_raw_artifacts_content_hash_key",
        "market_data_raw_artifacts",
        type_="unique",
    )
    op.create_index(
        "ix_market_data_raw_artifacts_content_hash",
        "market_data_raw_artifacts",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    raise NotImplementedError(
        "011_raw_fetch_obs is irreversible: duplicate content_hash rows "
        "cannot restore UNIQUE(content_hash)."
    )
