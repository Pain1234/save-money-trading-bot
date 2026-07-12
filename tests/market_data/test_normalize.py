"""Normalization boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_data.models import MarketTimeframe, RawCandle
from market_data.normalize import normalize_raw_candle
from market_data.timeframes import (
    daily_close,
    daily_open,
    monthly_close,
    monthly_open,
    weekly_close,
    weekly_open_containing,
)


def _raw(
    *,
    timeframe: MarketTimeframe,
    open_time: datetime,
    close_time: datetime,
) -> RawCandle:
    return RawCandle(
        provider_symbol="BTC",
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("102"),
        volume=Decimal("1000"),
        is_closed=True,
    )


def test_hyperliquid_daily_close_snaps_to_second_boundary() -> None:
    open_time = datetime(2025, 7, 13, 0, 0, tzinfo=UTC)
    close_time = datetime(2025, 7, 13, 23, 59, 59, 999000, tzinfo=UTC)
    raw = _raw(
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=close_time,
    )
    normalized = normalize_raw_candle(raw, close_time)
    assert normalized.open_time == daily_open(open_time)
    assert normalized.close_time == daily_close(open_time)


def test_hyperliquid_weekly_open_snaps_to_monday() -> None:
    thursday = datetime(2025, 7, 17, 0, 0, tzinfo=UTC)
    raw = _raw(
        timeframe=MarketTimeframe.WEEKLY,
        open_time=thursday,
        close_time=thursday,
    )
    monday = weekly_open_containing(thursday)
    normalized = normalize_raw_candle(raw, weekly_close(monday))
    assert normalized.open_time == monday
    assert normalized.close_time == weekly_close(monday)


def test_hyperliquid_monthly_open_snaps_to_first_day() -> None:
    mid_month = datetime(2025, 7, 17, 0, 0, tzinfo=UTC)
    raw = _raw(
        timeframe=MarketTimeframe.MONTHLY,
        open_time=mid_month,
        close_time=mid_month,
    )
    first = monthly_open(2025, 7)
    normalized = normalize_raw_candle(raw, monthly_close(first))
    assert normalized.open_time == first
    assert normalized.close_time == monthly_close(first)
