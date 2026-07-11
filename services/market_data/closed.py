"""Closed-candle filtering — look-ahead safe."""

from __future__ import annotations

from datetime import datetime

from market_data.models import NormalizedCandle
from market_data.timeframes import ensure_utc, is_candle_closed


def filter_closed_candles(
    candles: tuple[NormalizedCandle, ...],
    evaluation_time: datetime,
) -> tuple[NormalizedCandle, ...]:
    """Return candles closed at or before ``evaluation_time``."""
    evaluation_time = ensure_utc(evaluation_time)
    return tuple(
        c for c in candles if is_candle_closed(c.close_time, evaluation_time)
    )


def mark_closed_state(
    candle: NormalizedCandle,
    evaluation_time: datetime,
) -> NormalizedCandle:
    evaluation_time = ensure_utc(evaluation_time)
    closed = is_candle_closed(candle.close_time, evaluation_time)
    if candle.is_closed == closed:
        return candle
    return candle.model_copy(update={"is_closed": closed})
