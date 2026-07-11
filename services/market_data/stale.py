"""Timeframe-aware candle staleness."""

from __future__ import annotations

from datetime import datetime

from market_data.models import NormalizedCandle
from market_data.timeframes import ensure_utc, expected_close_time, is_candle_closed, next_open_time


def is_candle_data_stale(
    last_candle: NormalizedCandle | None,
    evaluation_time: datetime,
) -> bool:
    """Stale when the next expected period closed without a newer candle."""
    if last_candle is None:
        return True

    evaluation_time = ensure_utc(evaluation_time)
    next_open = next_open_time(last_candle.open_time, last_candle.timeframe)
    expected_next_close = expected_close_time(next_open, last_candle.timeframe)

    if not is_candle_closed(expected_next_close, evaluation_time):
        return False

    return last_candle.open_time < next_open
