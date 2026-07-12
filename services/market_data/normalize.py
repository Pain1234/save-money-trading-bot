"""Normalize provider candles to internal representation."""

from __future__ import annotations

from datetime import datetime

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle, RawCandle
from market_data.symbols import resolve_internal_symbol
from market_data.timeframes import (
    daily_close,
    daily_open,
    ensure_utc,
    is_candle_closed,
    monthly_close,
    monthly_open,
    weekly_close,
    weekly_open_containing,
)


def _canonical_time_bounds(raw: RawCandle) -> tuple[datetime, datetime]:
    """Map provider timestamps to internal UTC timeframe boundaries."""
    open_time = ensure_utc(raw.open_time)
    close_time = ensure_utc(raw.close_time)
    if raw.timeframe == MarketTimeframe.DAILY:
        canonical_open = daily_open(open_time)
        return canonical_open, daily_close(canonical_open)
    if raw.timeframe == MarketTimeframe.WEEKLY:
        canonical_open = weekly_open_containing(open_time)
        return canonical_open, weekly_close(canonical_open)
    if raw.timeframe == MarketTimeframe.MONTHLY:
        canonical_open = monthly_open(open_time.year, open_time.month)
        return canonical_open, monthly_close(canonical_open)
    return open_time, close_time


def normalize_raw_candle(raw: RawCandle, evaluation_time: datetime) -> NormalizedCandle:
    """Deterministic normalization from provider payload."""
    symbol = resolve_internal_symbol(raw.provider_symbol)
    open_time, close_time = _canonical_time_bounds(raw)
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
