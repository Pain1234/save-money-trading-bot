"""UTC timeframe boundaries and duration rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_data.models import MarketTimeframe


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware UTC")
    return dt.astimezone(UTC)


def daily_open(day: datetime) -> datetime:
    day = ensure_utc(day)
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


def daily_close(open_time: datetime) -> datetime:
    return ensure_utc(open_time).replace(hour=23, minute=59, second=59, microsecond=0)


def weekly_open_containing(day: datetime) -> datetime:
    """Monday 00:00 UTC of the week containing ``day``."""
    day = daily_open(day)
    monday_offset = day.weekday()
    return day - timedelta(days=monday_offset)


def weekly_close(open_time: datetime) -> datetime:
    """Sunday 23:59:59 UTC for week starting Monday ``open_time``."""
    open_time = ensure_utc(open_time)
    if open_time.weekday() != 0:
        raise ValueError("weekly open_time must be Monday 00:00 UTC")
    return open_time + timedelta(days=6, hours=23, minutes=59, seconds=59)


def monthly_open(year: int, month: int) -> datetime:
    return datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)


def monthly_close(open_time: datetime) -> datetime:
    open_time = ensure_utc(open_time)
    if open_time.day != 1 or open_time.hour != 0:
        raise ValueError("monthly open_time must be first day 00:00 UTC")
    if open_time.month == 12:
        next_month = datetime(open_time.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(open_time.year, open_time.month + 1, 1, tzinfo=UTC)
    return next_month - timedelta(seconds=1)


def expected_close_time(open_time: datetime, timeframe: MarketTimeframe) -> datetime:
    open_time = ensure_utc(open_time)
    if timeframe == MarketTimeframe.DAILY:
        return daily_close(open_time)
    if timeframe == MarketTimeframe.WEEKLY:
        return weekly_close(open_time)
    if timeframe == MarketTimeframe.MONTHLY:
        return monthly_close(open_time)
    raise ValueError(f"Unknown timeframe: {timeframe}")


def next_open_time(open_time: datetime, timeframe: MarketTimeframe) -> datetime:
    open_time = ensure_utc(open_time)
    if timeframe == MarketTimeframe.DAILY:
        return open_time + timedelta(days=1)
    if timeframe == MarketTimeframe.WEEKLY:
        return open_time + timedelta(days=7)
    if timeframe == MarketTimeframe.MONTHLY:
        if open_time.month == 12:
            return datetime(open_time.year + 1, 1, 1, tzinfo=UTC)
        return datetime(open_time.year, open_time.month + 1, 1, tzinfo=UTC)
    raise ValueError(f"Unknown timeframe: {timeframe}")


def is_valid_timeframe_duration(
    open_time: datetime,
    close_time: datetime,
    timeframe: MarketTimeframe,
) -> bool:
    expected = expected_close_time(open_time, timeframe)
    return ensure_utc(close_time) == expected


def is_candle_closed(close_time: datetime, evaluation_time: datetime) -> bool:
    """Closed when ``close_time <= evaluation_time`` (both UTC-aware)."""
    return ensure_utc(close_time) <= ensure_utc(evaluation_time)
