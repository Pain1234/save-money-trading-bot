"""Domain DTOs for the paper trading orchestrator (no ORM dependency)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from paper_trading.config import PaperTradingConfig
from paper_trading.enums import (
    PaperFillKind,
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionStatus,
    PaperSide,
    RuntimeStatus,
    SchedulerRunStatus,
    SignalType,
    TradeIntentStatus,
)
from paper_trading.ids import ensure_utc


def _validate_utc(dt: datetime) -> datetime:
    return ensure_utc(dt)


class RuntimeState(BaseModel):
    model_config = ConfigDict(frozen=True)

    instance_id: UUID
    status: RuntimeStatus
    last_error: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime
    kill_switch: bool = False
    paused: bool = False
    current_cycle_id: UUID | None = None
    version: int = Field(default=1, ge=1)

    @field_validator("started_at", "heartbeat_at", mode="before")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _validate_utc(value)


class StrategyEvaluationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: UUID
    symbol: str
    evaluation_time: datetime
    daily_candle_open_time: datetime
    weekly_candle_key: datetime
    monthly_candle_key: datetime
    daily_candle_key: datetime
    strategy_version: str
    regime_result: dict[str, Any]
    entry_result: dict[str, Any]
    rejection_reasons: tuple[str, ...] = Field(default_factory=tuple)
    deterministic_input_hash: str
    created_at: datetime

    @field_validator(
        "evaluation_time",
        "daily_candle_open_time",
        "weekly_candle_key",
        "monthly_candle_key",
        "daily_candle_key",
        "created_at",
        mode="before",
    )
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class TradeIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: UUID
    idempotency_key: str
    symbol: str
    side: PaperSide = PaperSide.LONG
    signal_type: SignalType
    signal_time: datetime
    scheduled_fill_time: datetime
    requested_entry: Decimal
    requested_stop: Decimal
    requested_quantity: Decimal | None = None
    approved_quantity: Decimal | None = None
    risk_amount: Decimal | None = None
    status: TradeIntentStatus
    strategy_evaluation_id: UUID
    rejection_reason: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "signal_time",
        "scheduled_fill_time",
        "created_at",
        "updated_at",
        mode="before",
    )
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class PaperOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_order_id: UUID
    intent_id: UUID
    symbol: str
    side: PaperSide = PaperSide.LONG
    order_type: PaperOrderType = PaperOrderType.MARKET_AT_OPEN
    requested_quantity: Decimal
    remaining_quantity: Decimal
    expected_fill_time: datetime
    status: PaperOrderStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("expected_fill_time", "created_at", "updated_at", mode="before")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @field_validator("remaining_quantity")
    @classmethod
    def validate_remaining(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("remaining_quantity must be >= 0")
        return value


class PaperFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    fill_id: UUID
    paper_order_id: UUID | None = None
    position_id: UUID | None = None
    fill_kind: PaperFillKind = PaperFillKind.ENTRY
    symbol: str
    side: PaperSide = PaperSide.LONG
    quantity: Decimal
    market_open_price: Decimal
    slippage: Decimal
    fill_price: Decimal
    fee: Decimal
    fill_time: datetime
    candle_key: datetime
    deterministic_fill_key: str
    fill_sequence: int = Field(default=0, ge=0)

    @field_validator("fill_time", "candle_key", mode="before")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @field_validator("quantity", "market_open_price", "fill_price")
    @classmethod
    def validate_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity and prices must be > 0")
        return value

    @model_validator(mode="after")
    def validate_kind_refs(self) -> PaperFill:
        if self.fill_kind == PaperFillKind.ENTRY:
            if self.paper_order_id is None:
                raise ValueError("ENTRY fill requires paper_order_id")
        elif self.fill_kind == PaperFillKind.EXIT:
            if self.position_id is None:
                raise ValueError("EXIT fill requires position_id")
        return self


class PaperPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    position_id: UUID
    symbol: str
    status: PaperPositionStatus
    quantity: Decimal
    average_entry_price: Decimal
    initial_stop: Decimal
    current_stop: Decimal
    highest_close_since_entry: Decimal
    entry_atr14: Decimal
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    margin_reserved: Decimal
    entry_intent_id: UUID
    opened_at: datetime
    closed_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @field_validator("opened_at", "closed_at", mode="before")
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _validate_utc(value)

    @field_validator("quantity", "average_entry_price", "entry_atr14")
    @classmethod
    def validate_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity, average_entry_price and entry_atr14 must be > 0")
        return value

    @model_validator(mode="after")
    def validate_invariants(self) -> PaperPosition:
        if self.current_stop < self.initial_stop:
            raise ValueError("current_stop must be >= initial_stop")
        if self.initial_stop >= self.average_entry_price:
            raise ValueError("initial_stop must be below average_entry_price for LONG")
        if self.status == PaperPositionStatus.CLOSED:
            if self.closed_at is None:
                raise ValueError("closed_at required when status is CLOSED")
        elif self.closed_at is not None:
            raise ValueError("closed_at must be null unless status is CLOSED")
        if self.status == PaperPositionStatus.OPEN and self.quantity <= 0:
            raise ValueError("open position quantity must be > 0")
        return self

    def side_long_stop_below_entry(self) -> bool:
        return self.initial_stop >= self.average_entry_price


class PositionStopEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_event_id: UUID
    position_id: UUID
    previous_stop: Decimal
    new_stop: Decimal
    highest_close: Decimal
    atr: Decimal
    evaluation_time: datetime
    reason: str

    @field_validator("evaluation_time", mode="before")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @model_validator(mode="after")
    def validate_monotonic(self) -> PositionStopEvent:
        if self.new_stop < self.previous_stop:
            raise ValueError("new_stop must be >= previous_stop")
        return self


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: UUID
    evaluation_time: datetime
    cash: Decimal
    margin_used: Decimal
    equity: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_open_risk: Decimal
    open_position_count: int = Field(ge=0)
    idempotency_key: str

    @field_validator("evaluation_time", mode="before")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class FundingEventRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    funding_event_id: UUID
    position_id: UUID
    symbol: str
    funding_rate: Decimal
    notional: Decimal
    amount: Decimal
    funding_time: datetime
    deterministic_key: str

    @field_validator("funding_time", mode="before")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class SchedulerRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    job_name: str
    scheduled_for: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: SchedulerRunStatus
    error: str | None = None
    idempotency_key: str
    recovery_of_run_id: UUID | None = None
    resolved_by_run_id: UUID | None = None

    @field_validator("scheduled_for", "started_at", "completed_at", mode="before")
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _validate_utc(value)


class PaperWalletState(BaseModel):
    model_config = ConfigDict(frozen=True)

    wallet_id: UUID
    cash: Decimal
    total_realized_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_funding: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    version: int = Field(default=1, ge=1)
    updated_at: datetime

    @field_validator("updated_at", mode="before")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    cycle_id: UUID | None = None
    payload_json: dict[str, Any]
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _validate_utc(value)


class PaperExecutionConfig(BaseModel):
    """Execution parameters derived from PaperTradingConfig (Phase 3)."""

    model_config = ConfigDict(frozen=True)

    fee_rate: Decimal = Field(ge=0, le=Decimal("0.01"))
    slippage_bps: Decimal = Field(ge=0, le=Decimal("100"))
    max_leverage: Decimal = Field(gt=0, le=Decimal("2"))

    @classmethod
    def from_trading_config(cls, config: PaperTradingConfig) -> PaperExecutionConfig:
        return cls(
            fee_rate=config.paper_fee_rate,
            slippage_bps=config.paper_slippage_bps,
            max_leverage=config.paper_max_leverage,
        )
