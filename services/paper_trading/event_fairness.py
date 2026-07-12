"""Persistent group-based market event fairness scheduling."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from market_data.timeframes import ensure_utc


class FairnessEvent(Protocol):
    event_type: object
    symbol: str
    candle_open_time: datetime

FAIRNESS_CURSOR_SINGLETON_ID = UUID("00000000-0000-0000-0000-000000000010")
DEFAULT_MIN_RETRY_INTERVAL_SECONDS = 1
MAX_RETRY_INTERVAL_SECONDS = 30

_SYMBOL_ORDER = {"BTC": 0, "ETH": 1, "SOL": 2}
_EVENT_ORDER = {
    "DAILY_OPEN_AVAILABLE": 0,
    "DAILY_LIVE_UPDATE": 1,
    "DAILY_CLOSED": 2,
    "WEEKLY_CLOSED": 3,
    "MONTHLY_CLOSED": 4,
}


def _compact_timestamp(dt: datetime) -> str:
    normalized = ensure_utc(dt)
    return normalized.strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class MarketEventGroupState:
    group_key: str
    event_type: str
    group_time: datetime
    next_attempt_at: datetime
    defer_count: int


def market_event_group_key(event: FairnessEvent) -> str:
    """Lifecycle group: event class + economic candle open/close time."""
    event_type = getattr(event.event_type, "value", str(event.event_type))
    return f"{event_type}:{_compact_timestamp(event.candle_open_time)}"


def group_events(candidates: Sequence[FairnessEvent]) -> dict[str, list[FairnessEvent]]:
    grouped: dict[str, list[FairnessEvent]] = {}
    for event in candidates:
        key = market_event_group_key(event)
        grouped.setdefault(key, []).append(event)
    for events in grouped.values():
        events.sort(key=lambda item: (_SYMBOL_ORDER.get(item.symbol, 99), item.symbol))
    return grouped


def ordered_group_keys(groups: dict[str, list[FairnessEvent]]) -> list[str]:
    return sorted(
        groups.keys(),
        key=lambda key: (
            _EVENT_ORDER.get(
                getattr(groups[key][0].event_type, "value", str(groups[key][0].event_type)),
                99,
            ),
            groups[key][0].candle_open_time,
            key,
        ),
    )


def eligible_group_keys(
    group_keys: list[str],
    *,
    evaluation_time: datetime,
    group_states: dict[str, MarketEventGroupState],
) -> list[str]:
    eligible: list[str] = []
    for key in group_keys:
        state = group_states.get(key)
        if not isinstance(state, MarketEventGroupState):
            eligible.append(key)
            continue
        if state.next_attempt_at <= evaluation_time:
            eligible.append(key)
    return eligible


def compute_retry_backoff_seconds(defer_count: int) -> int:
    bounded = min(max(defer_count, 1), 5)
    multiplier = DEFAULT_MIN_RETRY_INTERVAL_SECONDS * (2 ** (bounded - 1))
    return int(min(MAX_RETRY_INTERVAL_SECONDS, multiplier))


def next_retry_at(*, evaluation_time: datetime, defer_count: int) -> datetime:
    return evaluation_time + timedelta(seconds=compute_retry_backoff_seconds(defer_count))


def advance_group_rotation_cursor(
    *,
    cursor: int,
    eligible_group_count: int,
    groups_rotated: int,
    had_deferred: bool,
) -> int:
    if eligible_group_count <= 0:
        return cursor
    if had_deferred:
        return (cursor + 1) % eligible_group_count
    if groups_rotated <= 0:
        return cursor
    return (cursor + groups_rotated) % eligible_group_count
