"""Paper trading indexes including partial unique for open positions.

Revision ID: 003_indexes
Revises: 002_constraints
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_indexes"
down_revision: str | None = "002_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_strategy_evaluations_symbol_time",
        "strategy_evaluations",
        ["symbol", "evaluation_time"],
    )
    op.create_index(
        "ix_strategy_evaluations_daily_open",
        "strategy_evaluations",
        ["daily_candle_open_time"],
    )
    op.create_index(
        "ix_trade_intents_status_fill_time",
        "trade_intents",
        ["status", "scheduled_fill_time"],
    )
    op.create_index(
        "ix_trade_intents_symbol_signal_time",
        "trade_intents",
        ["symbol", "signal_time"],
    )
    op.create_index(
        "ix_paper_orders_status_fill_time",
        "paper_orders",
        ["status", "expected_fill_time"],
    )
    op.create_index("ix_paper_orders_symbol", "paper_orders", ["symbol"])
    op.create_index("ix_paper_fills_symbol_time", "paper_fills", ["symbol", "fill_time"])
    op.create_index("ix_paper_positions_status", "paper_positions", ["status"])
    op.create_index(
        "uq_paper_positions_open_symbol",
        "paper_positions",
        ["symbol"],
        unique=True,
        postgresql_where=sa.text("status IN ('OPEN', 'CLOSING')"),
    )
    op.create_index("ix_portfolio_snapshots_eval_time", "portfolio_snapshots", ["evaluation_time"])
    op.create_index("ix_audit_events_aggregate", "audit_events", ["aggregate_type", "aggregate_id"])
    op.create_index("ix_audit_events_cycle", "audit_events", ["cycle_id"])
    op.create_index("ix_audit_events_created", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_type", "audit_events", ["event_type"])
    op.create_index("ix_scheduler_runs_running", "scheduler_runs", ["status", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduler_runs_running", table_name="scheduler_runs")
    op.drop_index("ix_audit_events_type", table_name="audit_events")
    op.drop_index("ix_audit_events_created", table_name="audit_events")
    op.drop_index("ix_audit_events_cycle", table_name="audit_events")
    op.drop_index("ix_audit_events_aggregate", table_name="audit_events")
    op.drop_index("ix_portfolio_snapshots_eval_time", table_name="portfolio_snapshots")
    op.drop_index("uq_paper_positions_open_symbol", table_name="paper_positions")
    op.drop_index("ix_paper_positions_status", table_name="paper_positions")
    op.drop_index("ix_paper_fills_symbol_time", table_name="paper_fills")
    op.drop_index("ix_paper_orders_symbol", table_name="paper_orders")
    op.drop_index("ix_paper_orders_status_fill_time", table_name="paper_orders")
    op.drop_index("ix_trade_intents_symbol_signal_time", table_name="trade_intents")
    op.drop_index("ix_trade_intents_status_fill_time", table_name="trade_intents")
    op.drop_index("ix_strategy_evaluations_daily_open", table_name="strategy_evaluations")
    op.drop_index("ix_strategy_evaluations_symbol_time", table_name="strategy_evaluations")
