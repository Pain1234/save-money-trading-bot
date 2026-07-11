"""Paper trading constraints.

Revision ID: 002_constraints
Revises: 001_initial
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002_constraints"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_strategy_eval_version_symbol_daily",
        "strategy_evaluations",
        ["strategy_version", "symbol", "daily_candle_open_time"],
    )
    op.create_unique_constraint(
        "uq_trade_intent_idempotency_key", "trade_intents", ["idempotency_key"]
    )
    op.create_unique_constraint(
        "uq_trade_intent_eval_symbol_side_signal",
        "trade_intents",
        ["strategy_evaluation_id", "symbol", "side", "signal_type"],
    )
    op.create_unique_constraint("uq_paper_orders_intent_id", "paper_orders", ["intent_id"])
    op.create_unique_constraint(
        "uq_paper_fills_deterministic_key", "paper_fills", ["deterministic_fill_key"]
    )
    op.create_unique_constraint(
        "uq_paper_fills_order_candle_seq",
        "paper_fills",
        ["paper_order_id", "candle_key", "fill_sequence"],
    )
    op.create_unique_constraint(
        "uq_stop_history_position_eval",
        "position_stop_history",
        ["position_id", "evaluation_time"],
    )
    op.create_unique_constraint(
        "uq_funding_position_time", "funding_events", ["position_id", "funding_time"]
    )
    op.create_unique_constraint(
        "uq_funding_deterministic_key", "funding_events", ["deterministic_key"]
    )
    op.create_unique_constraint(
        "uq_scheduler_job_scheduled_for", "scheduler_runs", ["job_name", "scheduled_for"]
    )
    op.create_unique_constraint(
        "uq_scheduler_idempotency_key", "scheduler_runs", ["idempotency_key"]
    )

    op.create_check_constraint("ck_runtime_state_version", "runtime_state", "version >= 1")
    op.create_check_constraint("ck_paper_wallet_version", "paper_wallet", "version >= 1")
    op.create_check_constraint(
        "ck_paper_orders_remaining_nonneg", "paper_orders", "remaining_quantity >= 0"
    )
    op.create_check_constraint(
        "ck_paper_orders_requested_positive", "paper_orders", "requested_quantity > 0"
    )
    op.create_check_constraint("ck_paper_fills_quantity_positive", "paper_fills", "quantity > 0")
    op.create_check_constraint("ck_paper_fills_price_positive", "paper_fills", "fill_price > 0")
    op.create_check_constraint(
        "ck_paper_positions_quantity_positive", "paper_positions", "quantity > 0"
    )
    op.create_check_constraint(
        "ck_paper_positions_entry_positive", "paper_positions", "average_entry_price > 0"
    )
    op.create_check_constraint(
        "ck_paper_positions_stop_monotonic", "paper_positions", "current_stop >= initial_stop"
    )
    op.create_check_constraint("ck_paper_positions_version", "paper_positions", "version >= 1")
    op.create_check_constraint(
        "ck_stop_history_monotonic", "position_stop_history", "new_stop >= previous_stop"
    )
    op.create_check_constraint(
        "ck_portfolio_snapshots_open_count", "portfolio_snapshots", "open_position_count >= 0"
    )


def downgrade() -> None:
    for name, table in [
        ("ck_portfolio_snapshots_open_count", "portfolio_snapshots"),
        ("ck_stop_history_monotonic", "position_stop_history"),
        ("ck_paper_positions_version", "paper_positions"),
        ("ck_paper_positions_stop_monotonic", "paper_positions"),
        ("ck_paper_positions_entry_positive", "paper_positions"),
        ("ck_paper_positions_quantity_positive", "paper_positions"),
        ("ck_paper_fills_price_positive", "paper_fills"),
        ("ck_paper_fills_quantity_positive", "paper_fills"),
        ("ck_paper_orders_requested_positive", "paper_orders"),
        ("ck_paper_orders_remaining_nonneg", "paper_orders"),
        ("ck_paper_wallet_version", "paper_wallet"),
        ("ck_runtime_state_version", "runtime_state"),
    ]:
        op.drop_constraint(name, table, type_="check")

    for name, table in [
        ("uq_scheduler_idempotency_key", "scheduler_runs"),
        ("uq_scheduler_job_scheduled_for", "scheduler_runs"),
        ("uq_funding_deterministic_key", "funding_events"),
        ("uq_funding_position_time", "funding_events"),
        ("uq_stop_history_position_eval", "position_stop_history"),
        ("uq_paper_fills_order_candle_seq", "paper_fills"),
        ("uq_paper_fills_deterministic_key", "paper_fills"),
        ("uq_paper_orders_intent_id", "paper_orders"),
        ("uq_trade_intent_eval_symbol_side_signal", "trade_intents"),
        ("uq_trade_intent_idempotency_key", "trade_intents"),
        ("uq_strategy_eval_version_symbol_daily", "strategy_evaluations"),
    ]:
        op.drop_constraint(name, table, type_="unique")
