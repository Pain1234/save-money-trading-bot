"""Append-only market data dataset tables (ADR-013).

Revision ID: 010_market_data_datasets
Revises: 009_soak_run_identity
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_market_data_datasets"
down_revision: str | None = "009_soak_run_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_data_raw_artifacts",
        sa.Column("raw_dataset_id", sa.String(length=64), primary_key=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("storage_relpath", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("fetch_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_table(
        "market_data_datasets",
        sa.Column("dataset_id", sa.String(length=64), primary_key=True),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_dataset_id", sa.String(length=64), nullable=False),
        sa.Column("parent_dataset_id", sa.String(length=64), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("layer", sa.String(length=16), nullable=False, server_default="normalized"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_dataset_id"],
            ["market_data_raw_artifacts.raw_dataset_id"],
            name="fk_market_data_datasets_raw_dataset_id",
        ),
        sa.ForeignKeyConstraint(
            ["parent_dataset_id"],
            ["market_data_datasets.dataset_id"],
            name="fk_market_data_datasets_parent_dataset_id",
        ),
    )
    op.create_table(
        "market_data_normalized_candles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=False),
        sa.Column("timeframe", sa.String(length=4), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(38, 18), nullable=False),
        sa.Column("high", sa.Numeric(38, 18), nullable=False),
        sa.Column("low", sa.Numeric(38, 18), nullable=False),
        sa.Column("close", sa.Numeric(38, 18), nullable=False),
        sa.Column("volume", sa.Numeric(38, 18), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["market_data_datasets.dataset_id"],
            name="fk_market_data_normalized_candles_dataset_id",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "symbol",
            "timeframe",
            "open_time",
            name="uq_market_data_normalized_candles_key",
        ),
    )
    op.create_index(
        "ix_market_data_normalized_candles_dataset_id",
        "market_data_normalized_candles",
        ["dataset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_data_normalized_candles_dataset_id")
    op.drop_table("market_data_normalized_candles")
    op.drop_table("market_data_datasets")
    op.drop_table("market_data_raw_artifacts")
