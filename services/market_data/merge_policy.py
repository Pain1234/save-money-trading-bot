"""Native vs aggregated candle merge policy."""

from __future__ import annotations

from datetime import datetime

from market_data.models import (
    CandleConflict,
    CandleKey,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
)
from market_data.validation import candles_equal, sort_candles


def merge_native_and_aggregated(
    native: tuple[NormalizedCandle, ...],
    aggregated: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
) -> tuple[tuple[NormalizedCandle, ...], tuple[CandleConflict, ...]]:
    """Merge native and aggregated series without silent source preference."""
    by_open: dict[datetime, NormalizedCandle] = {
        c.open_time: c for c in native if c.symbol == symbol and c.timeframe == timeframe
    }
    conflicts: list[CandleConflict] = []

    for agg in aggregated:
        if agg.symbol != symbol or agg.timeframe != timeframe:
            continue
        existing = by_open.get(agg.open_time)
        if existing is None:
            by_open[agg.open_time] = agg
            continue
        if candles_equal(existing, agg):
            continue
        key = CandleKey(symbol=symbol, timeframe=timeframe, open_time=agg.open_time)
        conflicts.append(CandleConflict(key=key, existing=existing, incoming=agg))

    merged = sort_candles(tuple(by_open.values()))
    return merged, tuple(conflicts)
