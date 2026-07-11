# ruff: noqa: E402
"""Weekly and monthly aggregation tests."""

from __future__ import annotations

from market_data.aggregation import aggregate_monthly_from_daily, aggregate_weekly_from_daily
from market_data.timeframes import daily_open, monthly_open, weekly_open_containing

from tests.market_data.conftest import dt, make_daily_series


def test_complete_week_from_daily() -> None:
    monday = weekly_open_containing(dt(2024, 1, 3))
    dailies = make_daily_series(7, start=monday)
    weeks = aggregate_weekly_from_daily(dailies, dailies[0].symbol, dailies[-1].close_time)
    assert len(weeks) == 1
    assert weeks[0].open_time == monday


def test_incomplete_week_not_published() -> None:
    monday = weekly_open_containing(dt(2024, 1, 3))
    dailies = make_daily_series(5, start=monday)
    weeks = aggregate_weekly_from_daily(dailies, dailies[0].symbol, dailies[-1].close_time)
    assert weeks == ()


def test_complete_month_from_daily() -> None:
    start = monthly_open(2024, 1)
    count = 31
    dailies = make_daily_series(count, start=start)
    months = aggregate_monthly_from_daily(dailies, dailies[0].symbol, dailies[-1].close_time)
    assert len(months) == 1
    assert months[0].open_time == start


def test_incomplete_month_not_published() -> None:
    start = monthly_open(2024, 1)
    dailies = make_daily_series(10, start=start)
    months = aggregate_monthly_from_daily(dailies, dailies[0].symbol, dailies[-1].close_time)
    assert months == ()


def test_utc_week_boundary() -> None:
    sunday = dt(2024, 1, 7)
    monday = weekly_open_containing(sunday)
    assert monday.weekday() == 0
    dailies = make_daily_series(7, start=monday)
    weeks = aggregate_weekly_from_daily(dailies, dailies[0].symbol, dailies[-1].close_time)
    assert len(weeks) == 1


def test_utc_month_boundary() -> None:
    start = monthly_open(2024, 2)
    days_in_feb = 29 if start.year == 2024 else 28
    dailies = make_daily_series(days_in_feb, start=start)
    months = aggregate_monthly_from_daily(dailies, dailies[0].symbol, dailies[-1].close_time)
    assert len(months) == 1


def test_weekly_open_before_evaluation_excluded() -> None:
    monday = weekly_open_containing(dt(2024, 1, 1))
    dailies = make_daily_series(7, start=monday)
    mid_week = daily_open(dailies[3].open_time)
    weeks = aggregate_weekly_from_daily(dailies, dailies[0].symbol, mid_week)
    assert weeks == ()
