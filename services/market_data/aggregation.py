"""Weekly and monthly aggregation from daily candles."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.timeframes import (
    daily_open,
    ensure_utc,
    is_candle_closed,
    monthly_close,
    monthly_open,
    weekly_close,
    weekly_open_containing,
)
from market_data.validation import sort_candles


def _aggregate_bucket(
    dailies: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    bucket_open: datetime,
    bucket_close: datetime,
    evaluation_time: datetime,
    *,
    required_days: set[datetime],
) -> NormalizedCandle | None:
    evaluation_time = ensure_utc(evaluation_time)
    bucket_open = ensure_utc(bucket_open)
    bucket_close = ensure_utc(bucket_close)

    if not is_candle_closed(bucket_close, evaluation_time):
        return None

    members = tuple(d for d in dailies if bucket_open <= d.open_time <= bucket_close)
    if not members:
        return None

    present = {daily_open(d.open_time) for d in members}
    if present != required_days:
        return None

    ordered = sort_candles(members)
    return NormalizedCandle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=bucket_open,
        close_time=bucket_close,
        open=ordered[0].open,
        high=max(d.high for d in ordered),
        low=min(d.low for d in ordered),
        close=ordered[-1].close,
        volume=sum((d.volume for d in ordered), Decimal("0")),
        is_closed=True,
    )


def _day_range(start: datetime, count: int) -> set[datetime]:
    return {start + timedelta(days=i) for i in range(count)}


def _month_day_range(month_start: datetime) -> set[datetime]:
    month_start = ensure_utc(month_start)
    close = monthly_close(month_start)
    days: set[datetime] = set()
    cursor = month_start
    while cursor <= close.replace(hour=0, minute=0, second=0):
        days.add(cursor)
        cursor += timedelta(days=1)
    return days


def aggregate_weekly_from_daily(
    dailies: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    evaluation_time: datetime,
) -> tuple[NormalizedCandle, ...]:
    """Aggregate complete Monday–Sunday weeks from daily candles."""
    evaluation_time = ensure_utc(evaluation_time)
    dailies = sort_candles(tuple(d for d in dailies if d.symbol == symbol))
    if not dailies:
        return ()

    weeks: list[NormalizedCandle] = []
    first_day = daily_open(dailies[0].open_time)
    last_day = daily_open(dailies[-1].open_time)
    week_start = weekly_open_containing(first_day)

    while week_start <= last_day:
        week_close = weekly_close(week_start)
        required = _day_range(week_start, 7)
        agg = _aggregate_bucket(
            dailies,
            symbol,
            MarketTimeframe.WEEKLY,
            week_start,
            week_close,
            evaluation_time,
            required_days=required,
        )
        if agg is not None:
            weeks.append(agg)
        week_start += timedelta(days=7)

    return tuple(weeks)


def aggregate_monthly_from_daily(
    dailies: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    evaluation_time: datetime,
) -> tuple[NormalizedCandle, ...]:
    """Aggregate complete calendar months from daily candles."""
    evaluation_time = ensure_utc(evaluation_time)
    dailies = sort_candles(tuple(d for d in dailies if d.symbol == symbol))
    if not dailies:
        return ()

    months: list[NormalizedCandle] = []
    cursor = monthly_open(dailies[0].open_time.year, dailies[0].open_time.month)
    last_day = daily_open(dailies[-1].open_time)

    while cursor <= last_day:
        close = monthly_close(cursor)
        required = _month_day_range(cursor)
        agg = _aggregate_bucket(
            dailies,
            symbol,
            MarketTimeframe.MONTHLY,
            cursor,
            close,
            evaluation_time,
            required_days=required,
        )
        if agg is not None:
            months.append(agg)
        if cursor.month == 12:
            cursor = monthly_open(cursor.year + 1, 1)
        else:
            cursor = monthly_open(cursor.year, cursor.month + 1)

    return tuple(months)
