"""SQLAlchemy ORM models for paper trading persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from paper_trading.db.base import Base

NUMERIC_MONEY = Numeric(38, 18)
NUMERIC_RATE = Numeric(38, 8)

RUNTIME_SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WALLET_SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class RuntimeStateRow(Base):
    __tablename__ = "runtime_state"

    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    current_cycle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (CheckConstraint("version >= 1", name="ck_runtime_state_version"),)


class StrategyEvaluationRow(Base):
    __tablename__ = "strategy_evaluations"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    daily_candle_open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    weekly_candle_key: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    monthly_candle_key: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    daily_candle_key: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    regime_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    entry_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rejection_reasons: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    deterministic_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    intents: Mapped[list[TradeIntentRow]] = relationship(back_populates="evaluation")

    __table_args__ = (
        UniqueConstraint(
            "strategy_version",
            "symbol",
            "daily_candle_open_time",
            name="uq_strategy_eval_version_symbol_daily",
        ),
        Index("ix_strategy_evaluations_symbol_time", "symbol", "evaluation_time"),
        Index("ix_strategy_evaluations_daily_open", "daily_candle_open_time"),
    )


class TradeIntentRow(Base):
    __tablename__ = "trade_intents"

    intent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False, server_default="LONG")
    signal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_entry: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    requested_stop: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    requested_quantity: Mapped[Decimal | None] = mapped_column(NUMERIC_MONEY, nullable=True)
    approved_quantity: Mapped[Decimal | None] = mapped_column(NUMERIC_MONEY, nullable=True)
    risk_amount: Mapped[Decimal | None] = mapped_column(NUMERIC_MONEY, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_evaluations.evaluation_id"), nullable=False
    )
    rejection_reason: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evaluation: Mapped[StrategyEvaluationRow] = relationship(back_populates="intents")
    order: Mapped[PaperOrderRow | None] = relationship(back_populates="intent")

    __table_args__ = (
        UniqueConstraint(
            "strategy_evaluation_id",
            "symbol",
            "side",
            "signal_type",
            name="uq_trade_intent_eval_symbol_side_signal",
        ),
        Index("ix_trade_intents_status_fill_time", "status", "scheduled_fill_time"),
        Index("ix_trade_intents_symbol_signal_time", "symbol", "signal_time"),
    )


class PaperOrderRow(Base):
    __tablename__ = "paper_orders"

    paper_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_intents.intent_id"), nullable=False, unique=True
    )
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False, server_default="LONG")
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_quantity: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    expected_fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    intent: Mapped[TradeIntentRow] = relationship(back_populates="order")
    fills: Mapped[list[PaperFillRow]] = relationship(back_populates="order")

    __table_args__ = (
        CheckConstraint("remaining_quantity >= 0", name="ck_paper_orders_remaining_nonneg"),
        CheckConstraint("requested_quantity > 0", name="ck_paper_orders_requested_positive"),
        Index("ix_paper_orders_status_fill_time", "status", "expected_fill_time"),
        Index("ix_paper_orders_symbol", "symbol"),
    )


class PaperFillRow(Base):
    __tablename__ = "paper_fills"

    fill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    paper_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_orders.paper_order_id"), nullable=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_positions.position_id"), nullable=True
    )
    fill_kind: Mapped[str] = mapped_column(String(8), nullable=False, server_default="ENTRY")
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False, server_default="LONG")
    quantity: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    market_open_price: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    slippage: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    fee: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candle_key: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fill_sequence: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    deterministic_fill_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    order: Mapped[PaperOrderRow] = relationship(back_populates="fills")

    __table_args__ = (
        UniqueConstraint(
            "paper_order_id",
            "candle_key",
            "fill_sequence",
            name="uq_paper_fills_order_candle_seq",
        ),
        CheckConstraint("quantity > 0", name="ck_paper_fills_quantity_positive"),
        CheckConstraint("fill_price > 0", name="ck_paper_fills_price_positive"),
        CheckConstraint(
            "(fill_kind = 'ENTRY' AND paper_order_id IS NOT NULL AND position_id IS NULL) "
            "OR (fill_kind = 'EXIT' AND position_id IS NOT NULL)",
            name="ck_paper_fills_kind_refs",
        ),
        Index("ix_paper_fills_symbol_time", "symbol", "fill_time"),
    )


class PaperPositionRow(Base):
    __tablename__ = "paper_positions"

    position_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    initial_stop: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    current_stop: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    highest_close_since_entry: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    entry_atr14: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        NUMERIC_MONEY, nullable=False, server_default=text("0")
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        NUMERIC_MONEY, nullable=False, server_default=text("0")
    )
    margin_reserved: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    entry_intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_intents.intent_id"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    stop_events: Mapped[list[PositionStopHistoryRow]] = relationship(back_populates="position")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_paper_positions_quantity_positive"),
        CheckConstraint("average_entry_price > 0", name="ck_paper_positions_entry_positive"),
        CheckConstraint("entry_atr14 > 0", name="ck_paper_positions_entry_atr_positive"),
        CheckConstraint("current_stop >= initial_stop", name="ck_paper_positions_stop_monotonic"),
        CheckConstraint("version >= 1", name="ck_paper_positions_version"),
        Index(
            "uq_paper_positions_open_symbol",
            "symbol",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'CLOSING')"),
        ),
        Index("ix_paper_positions_status", "status"),
    )


class PositionStopHistoryRow(Base):
    __tablename__ = "position_stop_history"

    stop_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_positions.position_id"), nullable=False
    )
    previous_stop: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    new_stop: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    highest_close: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    atr: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)

    position: Mapped[PaperPositionRow] = relationship(back_populates="stop_events")

    __table_args__ = (
        UniqueConstraint("position_id", "evaluation_time", name="uq_stop_history_position_eval"),
        CheckConstraint("new_stop >= previous_stop", name="ck_stop_history_monotonic"),
    )


class PortfolioSnapshotRow(Base):
    __tablename__ = "portfolio_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cash: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    equity: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    total_open_risk: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    open_position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("open_position_count >= 0", name="ck_portfolio_snapshots_open_count"),
        Index("ix_portfolio_snapshots_eval_time", "evaluation_time"),
        UniqueConstraint("idempotency_key", name="uq_portfolio_snapshots_idempotency"),
    )


class FundingEventRow(Base):
    __tablename__ = "funding_events"

    funding_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_positions.position_id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    funding_rate: Mapped[Decimal] = mapped_column(NUMERIC_RATE, nullable=False)
    notional: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    amount: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    funding_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deterministic_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    __table_args__ = (
        UniqueConstraint("position_id", "funding_time", name="uq_funding_position_time"),
    )


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_audit_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_audit_events_cycle", "cycle_id"),
        Index("ix_audit_events_created", "created_at"),
        Index("ix_audit_events_type", "event_type"),
    )


class SchedulerRunRow(Base):
    __tablename__ = "scheduler_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    recovery_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduler_runs.run_id"),
        nullable=True,
    )
    resolved_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduler_runs.run_id"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("job_name", "scheduled_for", name="uq_scheduler_job_scheduled_for"),
        Index("ix_scheduler_runs_running", "status", "started_at"),
        Index("ix_scheduler_runs_recovery_of", "recovery_of_run_id"),
    )


class PaperWalletRow(Base):
    __tablename__ = "paper_wallet"

    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cash: Mapped[Decimal] = mapped_column(NUMERIC_MONEY, nullable=False)
    total_realized_pnl: Mapped[Decimal] = mapped_column(
        NUMERIC_MONEY, nullable=False, server_default=text("0")
    )
    total_fees: Mapped[Decimal] = mapped_column(
        NUMERIC_MONEY, nullable=False, server_default=text("0")
    )
    total_funding: Mapped[Decimal] = mapped_column(
        NUMERIC_MONEY, nullable=False, server_default=text("0")
    )
    total_slippage: Mapped[Decimal] = mapped_column(
        NUMERIC_MONEY, nullable=False, server_default=text("0")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("version >= 1", name="ck_paper_wallet_version"),)
