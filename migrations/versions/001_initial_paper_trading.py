"""Initial paper trading tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUMERIC_MONEY = sa.Numeric(38, 18)
NUMERIC_RATE = sa.Numeric(38, 8)


def upgrade() -> None:
    op.create_table(
        "runtime_state",
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_table(
        "paper_wallet",
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cash", NUMERIC_MONEY, nullable=False),
        sa.Column("total_realized_pnl", NUMERIC_MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("total_fees", NUMERIC_MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("total_funding", NUMERIC_MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("total_slippage", NUMERIC_MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "strategy_evaluations",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_candle_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weekly_candle_key", sa.DateTime(timezone=True), nullable=False),
        sa.Column("monthly_candle_key", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_candle_key", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_version", sa.String(16), nullable=False),
        sa.Column("regime_result", postgresql.JSONB(), nullable=False),
        sa.Column("entry_result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "rejection_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("deterministic_input_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trade_intents",
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("side", sa.String(8), nullable=False, server_default="LONG"),
        sa.Column("signal_type", sa.String(16), nullable=False),
        sa.Column("signal_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_fill_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_entry", NUMERIC_MONEY, nullable=False),
        sa.Column("requested_stop", NUMERIC_MONEY, nullable=False),
        sa.Column("requested_quantity", NUMERIC_MONEY, nullable=True),
        sa.Column("approved_quantity", NUMERIC_MONEY, nullable=True),
        sa.Column("risk_amount", NUMERIC_MONEY, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("strategy_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rejection_reason", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["strategy_evaluation_id"], ["strategy_evaluations.evaluation_id"]),
    )
    op.create_table(
        "paper_orders",
        sa.Column("paper_order_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("side", sa.String(8), nullable=False, server_default="LONG"),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("requested_quantity", NUMERIC_MONEY, nullable=False),
        sa.Column("remaining_quantity", NUMERIC_MONEY, nullable=False),
        sa.Column("expected_fill_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intent_id"], ["trade_intents.intent_id"]),
    )
    op.create_table(
        "paper_fills",
        sa.Column("fill_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("side", sa.String(8), nullable=False, server_default="LONG"),
        sa.Column("quantity", NUMERIC_MONEY, nullable=False),
        sa.Column("market_open_price", NUMERIC_MONEY, nullable=False),
        sa.Column("slippage", NUMERIC_MONEY, nullable=False),
        sa.Column("fill_price", NUMERIC_MONEY, nullable=False),
        sa.Column("fee", NUMERIC_MONEY, nullable=False),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candle_key", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fill_sequence", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("deterministic_fill_key", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["paper_order_id"], ["paper_orders.paper_order_id"]),
    )
    op.create_table(
        "paper_positions",
        sa.Column("position_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("quantity", NUMERIC_MONEY, nullable=False),
        sa.Column("average_entry_price", NUMERIC_MONEY, nullable=False),
        sa.Column("initial_stop", NUMERIC_MONEY, nullable=False),
        sa.Column("current_stop", NUMERIC_MONEY, nullable=False),
        sa.Column("highest_close_since_entry", NUMERIC_MONEY, nullable=False),
        sa.Column("realized_pnl", NUMERIC_MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("unrealized_pnl", NUMERIC_MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("margin_reserved", NUMERIC_MONEY, nullable=False),
        sa.Column("entry_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["entry_intent_id"], ["trade_intents.intent_id"]),
    )
    op.create_table(
        "position_stop_history",
        sa.Column("stop_event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_stop", NUMERIC_MONEY, nullable=False),
        sa.Column("new_stop", NUMERIC_MONEY, nullable=False),
        sa.Column("highest_close", NUMERIC_MONEY, nullable=False),
        sa.Column("atr", NUMERIC_MONEY, nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["paper_positions.position_id"]),
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash", NUMERIC_MONEY, nullable=False),
        sa.Column("margin_used", NUMERIC_MONEY, nullable=False),
        sa.Column("equity", NUMERIC_MONEY, nullable=False),
        sa.Column("unrealized_pnl", NUMERIC_MONEY, nullable=False),
        sa.Column("realized_pnl", NUMERIC_MONEY, nullable=False),
        sa.Column("total_open_risk", NUMERIC_MONEY, nullable=False),
        sa.Column("open_position_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "funding_events",
        sa.Column("funding_event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("funding_rate", NUMERIC_RATE, nullable=False),
        sa.Column("notional", NUMERIC_MONEY, nullable=False),
        sa.Column("amount", NUMERIC_MONEY, nullable=False),
        sa.Column("funding_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deterministic_key", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["paper_positions.position_id"]),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scheduler_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scheduler_runs")
    op.drop_table("audit_events")
    op.drop_table("funding_events")
    op.drop_table("portfolio_snapshots")
    op.drop_table("position_stop_history")
    op.drop_table("paper_positions")
    op.drop_table("paper_fills")
    op.drop_table("paper_orders")
    op.drop_table("trade_intents")
    op.drop_table("strategy_evaluations")
    op.drop_table("paper_wallet")
    op.drop_table("runtime_state")
