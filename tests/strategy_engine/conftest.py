"""Shared test fixtures for strategy engine."""

from __future__ import annotations

import sys
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

# ruff: noqa: E402
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from strategy_engine.models import Candle, CandleSeries, Timeframe

UTC = UTC


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def daily_close_time(open_time: datetime) -> datetime:
    return open_time.replace(hour=23, minute=59, second=59)


def make_daily_candle(
    symbol: str,
    open_time: datetime,
    o: str,
    h: str,
    low: str,
    c: str,
    vol: str = "1000",
    *,
    is_closed: bool = True,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.DAILY,
        open_time=open_time,
        close_time=daily_close_time(open_time),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(vol),
        is_closed=is_closed,
    )


def make_weekly_candle(
    symbol: str,
    open_time: datetime,
    o: str,
    h: str,
    low: str,
    c: str,
    vol: str = "5000",
    *,
    is_closed: bool = True,
) -> Candle:
    close_time = open_time + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.WEEKLY,
        open_time=open_time,
        close_time=close_time,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(vol),
        is_closed=is_closed,
    )


def make_monthly_candle(
    symbol: str,
    year: int,
    month: int,
    o: str,
    h: str,
    low: str,
    c: str,
    vol: str = "20000",
    *,
    is_closed: bool = True,
) -> Candle:
    open_time = dt(year, month, 1)
    if month == 12:
        next_month = dt(year + 1, 1, 1)
    else:
        next_month = dt(year, month + 1, 1)
    close_time = next_month - timedelta(seconds=1)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.MONTHLY,
        open_time=open_time,
        close_time=close_time,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(vol),
        is_closed=is_closed,
    )


def build_flat_daily_series(
    symbol: str,
    count: int,
    base_price: str = "100",
    base_volume: str = "1000",
    start: datetime | None = None,
) -> CandleSeries:
    start = start or dt(2024, 1, 1)
    candles: list[Candle] = []
    for i in range(count):
        open_time = start + timedelta(days=i)
        candles.append(
            make_daily_candle(
                symbol,
                open_time,
                base_price,
                str(Decimal(base_price) + Decimal("2")),
                str(Decimal(base_price) - Decimal("1")),
                base_price,
                base_volume,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=Timeframe.DAILY, candles=tuple(candles))


def build_flat_weekly_series(
    symbol: str,
    count: int,
    base_price: str = "100",
    start: datetime | None = None,
) -> CandleSeries:
    start = start or dt(2023, 1, 2)
    candles: list[Candle] = []
    for i in range(count):
        open_time = start + timedelta(weeks=i)
        candles.append(
            make_weekly_candle(
                symbol,
                open_time,
                base_price,
                str(Decimal(base_price) + Decimal("5")),
                str(Decimal(base_price) - Decimal("3")),
                base_price,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=Timeframe.WEEKLY, candles=tuple(candles))


def build_rising_weekly_series(
    symbol: str,
    count: int,
    start_price: Decimal = Decimal("100"),
) -> CandleSeries:
    candles: list[Candle] = []
    start = dt(2023, 1, 2)
    price = start_price
    for i in range(count):
        open_time = start + timedelta(weeks=i)
        p = str(price)
        candles.append(
            make_weekly_candle(
                symbol,
                open_time,
                p,
                str(price + Decimal("5")),
                str(price - Decimal("3")),
                p,
            )
        )
        price += Decimal("5")
    return CandleSeries(symbol=symbol, timeframe=Timeframe.WEEKLY, candles=tuple(candles))


def build_rising_monthly_series(
    symbol: str,
    count: int,
    start_price: Decimal = Decimal("100"),
) -> CandleSeries:
    candles: list[Candle] = []
    year, month = 2020, 1
    price = start_price
    for _ in range(count):
        p = str(price)
        candles.append(make_monthly_candle(symbol, year, month, p, p, p, p))
        price += Decimal("10")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return CandleSeries(symbol=symbol, timeframe=Timeframe.MONTHLY, candles=tuple(candles))
