# ruff: noqa: E402
"""Shared fixtures for market data tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle, RawCandle
from market_data.symbols import to_provider_symbol
from market_data.timeframes import (
    daily_close,
    daily_open,
    monthly_close,
    monthly_open,
    weekly_close,
    weekly_open_containing,
)

UTC = UTC


def dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


def make_daily(
    symbol: MarketSymbol = MarketSymbol.BTC,
    day: datetime | None = None,
    *,
    o: str = "100",
    h: str = "101",
    low: str = "99",
    c: str = "100",
    vol: str = "1000",
    is_closed: bool = True,
) -> NormalizedCandle:
    day = daily_open(day or dt(2024, 1, 1))
    return NormalizedCandle(
        symbol=symbol,
        timeframe=MarketTimeframe.DAILY,
        open_time=day,
        close_time=daily_close(day),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(vol),
        is_closed=is_closed,
    )


def make_daily_series(
    count: int,
    start: datetime | None = None,
    symbol: MarketSymbol = MarketSymbol.BTC,
) -> tuple[NormalizedCandle, ...]:
    start = daily_open(start or dt(2024, 1, 1))
    return tuple(make_daily(symbol, start + timedelta(days=i)) for i in range(count))


def make_weekly(
    symbol: MarketSymbol = MarketSymbol.BTC,
    monday: datetime | None = None,
    *,
    complete_from_daily: tuple[NormalizedCandle, ...] | None = None,
) -> NormalizedCandle:
    monday = weekly_open_containing(monday or dt(2024, 1, 1))
    if complete_from_daily:
        from market_data.aggregation import aggregate_weekly_from_daily

        agg = aggregate_weekly_from_daily(
            complete_from_daily, symbol, weekly_close(monday)
        )
        return agg[0]
    return NormalizedCandle(
        symbol=symbol,
        timeframe=MarketTimeframe.WEEKLY,
        open_time=monday,
        close_time=weekly_close(monday),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("102"),
        volume=Decimal("7000"),
        is_closed=True,
    )


def make_monthly(
    symbol: MarketSymbol = MarketSymbol.BTC,
    year: int = 2024,
    month: int = 1,
    *,
    complete_from_daily: tuple[NormalizedCandle, ...] | None = None,
) -> NormalizedCandle:
    open_time = monthly_open(year, month)
    if complete_from_daily:
        from market_data.aggregation import aggregate_monthly_from_daily

        agg = aggregate_monthly_from_daily(
            complete_from_daily, symbol, monthly_close(open_time)
        )
        return agg[0]
    return NormalizedCandle(
        symbol=symbol,
        timeframe=MarketTimeframe.MONTHLY,
        open_time=open_time,
        close_time=monthly_close(open_time),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("30000"),
        is_closed=True,
    )


def to_raw(candle: NormalizedCandle) -> RawCandle:
    return RawCandle(
        provider_symbol=to_provider_symbol(candle.symbol),
        timeframe=candle.timeframe,
        open_time=candle.open_time,
        close_time=candle.close_time,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        is_closed=candle.is_closed,
    )
