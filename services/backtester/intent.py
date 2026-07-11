"""Deterministic client intent ID generation."""

from __future__ import annotations

from datetime import datetime

from strategy_engine.models import EntryType


def build_client_intent_id(
    symbol: str,
    strategy_version: str,
    signal_time: datetime,
    entry_type: EntryType,
) -> str:
    """Stable intent ID: symbol + strategy_version + signal_timestamp + entry_type."""
    ts = signal_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{symbol}:{strategy_version}:{ts}:{entry_type.value}"
