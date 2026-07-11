"""Deterministic idempotency keys and input hashes for paper trading."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backtester.intent import build_client_intent_id
from strategy_engine.models import EntryType

from paper_trading.enums import PaperSide, SignalType


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC, rejecting naive values."""
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC required)")
    return dt.astimezone(UTC)


def format_utc_timestamp(dt: datetime) -> str:
    """Canonical UTC ISO-8601 with Z suffix."""
    normalized = ensure_utc(dt)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def strategy_evaluation_key(
    strategy_version: str,
    symbol: str,
    daily_candle_open_time: datetime,
) -> str:
    """Unique key for one evaluation per strategy version, symbol, and daily candle."""
    ts = format_utc_timestamp(daily_candle_open_time)
    return f"{strategy_version}:{symbol}:{ts}"


def trade_intent_key(
    symbol: str,
    strategy_version: str,
    signal_time: datetime,
    signal_type: SignalType,
) -> str:
    """Intent idempotency key compatible with backtester build_client_intent_id."""
    entry_type = EntryType(signal_type.value)
    return build_client_intent_id(symbol, strategy_version, ensure_utc(signal_time), entry_type)


def paper_fill_key(
    paper_order_id: UUID,
    fill_candle_open_time: datetime,
    fill_sequence: int = 0,
) -> str:
    """Unique key for one fill per order, candle, and sequence."""
    ts = format_utc_timestamp(fill_candle_open_time)
    return f"{paper_order_id}:{ts}:{fill_sequence}"


def funding_event_key(position_id: UUID, funding_time: datetime) -> str:
    """Unique key for one funding event per position and timestamp."""
    ts = format_utc_timestamp(funding_time)
    return f"{position_id}:{ts}"


def scheduler_run_key(job_name: str, scheduled_for: datetime) -> str:
    """Unique key for one scheduler run per job and scheduled market time."""
    ts = format_utc_timestamp(scheduled_for)
    return f"{job_name}:{ts}"


def stop_update_key(position_id: UUID, evaluation_time: datetime) -> str:
    """Unique key for one stop update per position and evaluation time."""
    ts = format_utc_timestamp(evaluation_time)
    return f"{position_id}:{ts}"


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return format_utc_timestamp(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported type for deterministic hash: {type(value)!r}")


def deterministic_input_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON with sorted keys (order-independent)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def signal_type_to_entry_type(signal_type: SignalType) -> EntryType:
    """Map paper trading signal type to strategy engine entry type."""
    return EntryType(signal_type.value)


def entry_type_to_signal_type(entry_type: EntryType) -> SignalType:
    """Map strategy engine entry type to paper trading signal type."""
    return SignalType(entry_type.value)


def paper_side_to_trade_side(side: PaperSide) -> str:
    """Return trade side string for persistence."""
    return side.value
