"""Normalize provider candles to internal representation."""

from __future__ import annotations

from datetime import datetime

from market_data.models import MarketSymbol, NormalizedCandle, RawCandle
from market_data.symbols import resolve_internal_symbol
from market_data.timeframes import ensure_utc, is_candle_closed


def normalize_raw_candle(raw: RawCandle, evaluation_time: datetime) -> NormalizedCandle:
    """Deterministic normalization from provider payload."""
    symbol = resolve_internal_symbol(raw.provider_symbol)
    open_time = ensure_utc(raw.open_time)
    close_time = ensure_utc(raw.close_time)
    evaluation_time = ensure_utc(evaluation_time)
    closed = raw.is_closed and is_candle_closed(close_time, evaluation_time)
    return NormalizedCandle(
        symbol=symbol,
        timeframe=raw.timeframe,
        open_time=open_time,
        close_time=close_time,
        open=raw.open,
        high=raw.high,
        low=raw.low,
        close=raw.close,
        volume=raw.volume,
        is_closed=closed,
    )


def normalize_batch(
    raws: tuple[RawCandle, ...],
    evaluation_time: datetime,
    *,
    expected_symbol: MarketSymbol | None = None,
) -> tuple[NormalizedCandle, ...]:
    normalized = tuple(normalize_raw_candle(r, evaluation_time) for r in raws)
    if expected_symbol is not None:
        for candle in normalized:
            if candle.symbol != expected_symbol:
                raise ValueError(f"Expected symbol {expected_symbol}, got {candle.symbol}")
    return normalized
