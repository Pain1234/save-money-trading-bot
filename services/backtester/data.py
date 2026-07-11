"""Historical data slicing — look-ahead safe."""

from __future__ import annotations

from datetime import datetime, timedelta

from strategy_engine.models import Candle, CandleSeries, Timeframe


def slice_closed_candles(
    candles: tuple[Candle, ...],
    as_of: datetime,
) -> tuple[Candle, ...]:
    """Return candles closed at or before as_of."""
    return tuple(c for c in candles if c.is_closed and c.close_time <= as_of)


def build_candle_series(
    symbol: str,
    timeframe: Timeframe,
    candles: tuple[Candle, ...],
    as_of: datetime,
) -> CandleSeries:
    closed = slice_closed_candles(candles, as_of)
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=closed)


def evaluation_time_for_daily(candle: Candle) -> datetime:
    """Daily close event + 5s buffer (Strategy Spec §2.3)."""
    return candle.close_time + timedelta(seconds=5)


def validate_chronological(candles: tuple[Candle, ...]) -> list[str]:
    warnings: list[str] = []
    seen: set[datetime] = set()
    prev: datetime | None = None
    for c in candles:
        if c.open_time in seen:
            warnings.append(f"duplicate candle {c.symbol} {c.open_time.isoformat()}")
        seen.add(c.open_time)
        if prev is not None and c.open_time <= prev:
            warnings.append(f"unsorted candle {c.symbol} {c.open_time.isoformat()}")
        prev = c.open_time
        if not c.is_closed:
            warnings.append(f"open candle {c.symbol} {c.open_time.isoformat()}")
    return warnings
