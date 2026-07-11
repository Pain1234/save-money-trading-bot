"""Gap detection for candle series."""

from __future__ import annotations

from datetime import datetime

from market_data.models import CandleGap, MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.timeframes import ensure_utc, expected_close_time, next_open_time
from market_data.validation import sort_candles


def detect_gaps(
    candles: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
) -> tuple[CandleGap, ...]:
    """Detect missing candles between consecutive opens up to ``evaluation_time``."""
    evaluation_time = ensure_utc(evaluation_time)
    sorted_candles = sort_candles(candles)
    gaps: list[CandleGap] = []

    for i in range(len(sorted_candles) - 1):
        current = sorted_candles[i]
        nxt = sorted_candles[i + 1]
        expected_next = next_open_time(current.open_time, timeframe)
        cursor = expected_next
        while cursor < nxt.open_time:
            gaps.append(
                CandleGap(
                    symbol=symbol,
                    timeframe=timeframe,
                    missing_open_time=cursor,
                    expected_close_time=expected_close_time(cursor, timeframe),
                )
            )
            cursor = next_open_time(cursor, timeframe)

    if sorted_candles:
        last = sorted_candles[-1]
        cursor = next_open_time(last.open_time, timeframe)
        while cursor <= evaluation_time:
            close = expected_close_time(cursor, timeframe)
            if close > evaluation_time:
                break
            gaps.append(
                CandleGap(
                    symbol=symbol,
                    timeframe=timeframe,
                    missing_open_time=cursor,
                    expected_close_time=close,
                )
            )
            cursor = next_open_time(cursor, timeframe)

    return tuple(gaps)
