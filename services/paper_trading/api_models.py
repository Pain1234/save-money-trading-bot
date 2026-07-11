"""Pydantic response models for the paper trading API."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_PAGE_LIMIT = 100


def format_decimal(value: Decimal) -> str:
    return str(value)


def format_utc(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    return normalized.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def format_uuid(value: UUID) -> str:
    return str(value)


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("cursor must decode to object")
        return data
    except Exception as exc:
        raise ValueError("invalid cursor") from exc


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = "ok"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    process_liveness: bool
    runtime_readiness: bool
    entry_readiness: bool
    market_data_ready: bool
    database_ready: bool
    migration_at_head: bool
    advisory_lock_held: bool
    paused: bool
    kill_switch: bool
    reasons: tuple[str, ...] = Field(default_factory=tuple)
    last_error: str | None = None


class RuntimeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instance_id: str
    status: str
    last_error: str | None
    started_at: str | None
    heartbeat_at: str
    kill_switch: bool
    paused: bool
    current_cycle_id: str | None
    version: int


class WalletResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    wallet_id: str
    cash: str
    total_realized_pnl: str
    total_fees: str
    total_funding: str
    total_slippage: str
    version: int
    updated_at: str


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str | None
    evaluation_time: str | None
    cash: str | None
    margin_used: str | None
    equity: str | None
    unrealized_pnl: str | None
    realized_pnl: str | None
    total_open_risk: str | None
    open_position_count: int | None


class PositionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    status: str
    quantity: str
    average_entry_price: str
    initial_stop: str
    current_stop: str
    highest_close_since_entry: str
    entry_atr14: str
    realized_pnl: str
    unrealized_pnl: str
    margin_reserved: str
    entry_intent_id: str
    opened_at: str
    closed_at: str | None
    version: int


class IntentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    idempotency_key: str
    symbol: str
    side: str
    signal_type: str
    signal_time: str
    scheduled_fill_time: str
    requested_entry: str
    requested_stop: str
    status: str
    strategy_evaluation_id: str
    created_at: str
    updated_at: str


class OrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_order_id: str
    intent_id: str
    symbol: str
    side: str
    order_type: str
    requested_quantity: str
    remaining_quantity: str
    expected_fill_time: str
    status: str
    created_at: str
    updated_at: str


class FillResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    fill_id: str
    paper_order_id: str
    symbol: str
    side: str
    quantity: str
    market_open_price: str
    slippage: str
    fill_price: str
    fee: str
    fill_time: str
    candle_key: str
    fill_sequence: int
    deterministic_fill_key: str


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    symbol: str
    evaluation_time: str
    daily_candle_open_time: str
    strategy_version: str
    created_at: str


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    cycle_id: str | None
    payload_json: dict[str, Any]
    created_at: str


class SchedulerRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    job_name: str
    scheduled_for: str
    started_at: str | None
    completed_at: str | None
    status: str
    error: str | None
    idempotency_key: str


class PaginatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[Any]
    next_cursor: str | None
    limit: int


class ControlResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    message: str


class RunCycleRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_name: str
    scheduled_for: datetime

    def validate_scheduled_for(self) -> datetime:
        if self.scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware UTC")
        return self.scheduled_for.astimezone(UTC)
