# ruff: noqa: E402
"""Look-ahead protection tests."""

from __future__ import annotations

from market_data.bundle import get_strategy_bundle
from market_data.closed import filter_closed_candles
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import (
    daily_close,
    daily_open,
    monthly_open,
    weekly_close,
    weekly_open_containing,
)

from tests.market_data.conftest import dt, make_daily, make_daily_series


def _repo_with(*candles) -> InMemoryCandleRepository:
    repo = InMemoryCandleRepository()
    repo.upsert_many(candles)
    return repo


def test_open_daily_excluded_from_bundle() -> None:
    closed = make_daily(day=dt(2024, 1, 1))
    open_candle = make_daily(day=dt(2024, 1, 2), is_closed=False)
    repo = _repo_with(closed, open_candle)
    bundle = get_strategy_bundle(
        repo,
        MarketSymbol.BTC,
        closed.close_time,
        daily_minimum=1,
        weekly_minimum=0,
        monthly_minimum=0,
    )
    assert all(c.is_closed for c in bundle.daily.candles)
    assert bundle.daily.candles[-1].open_time == closed.open_time


def test_future_daily_excluded() -> None:
    past = make_daily(day=dt(2024, 1, 1))
    future = make_daily(day=dt(2024, 1, 5))
    repo = _repo_with(past, future)
    bundle = get_strategy_bundle(
        repo,
        MarketSymbol.BTC,
        past.close_time,
        daily_minimum=1,
        weekly_minimum=0,
        monthly_minimum=0,
    )
    assert len(bundle.daily.candles) == 1


def test_weekly_before_week_close_excluded() -> None:
    monday = weekly_open_containing(dt(2024, 1, 3))
    dailies = make_daily_series(7, start=monday)
    repo = _repo_with(*dailies)
    mid = daily_open(dailies[3].open_time)
    bundle = get_strategy_bundle(
        repo, MarketSymbol.BTC, mid, daily_minimum=1, weekly_minimum=0, monthly_minimum=0
    )
    assert bundle.weekly.length == 0


def test_monthly_before_month_close_excluded() -> None:
    start = monthly_open(2024, 1)
    dailies = make_daily_series(15, start=start)
    repo = _repo_with(*dailies)
    eval_time = daily_close(dailies[14].open_time)
    bundle = get_strategy_bundle(
        repo, MarketSymbol.BTC, eval_time, daily_minimum=1, weekly_minimum=0, monthly_minimum=0
    )
    assert bundle.monthly.length == 0


def test_evaluation_exactly_at_daily_close() -> None:
    candle = make_daily(day=dt(2024, 1, 1))
    filtered = filter_closed_candles((candle,), candle.close_time)
    assert len(filtered) == 1


def test_utc_day_boundary() -> None:
    day1 = make_daily(day=dt(2024, 1, 1))
    day2 = make_daily(day=dt(2024, 1, 2))
    repo = _repo_with(day1, day2)
    bundle = get_strategy_bundle(
        repo,
        MarketSymbol.BTC,
        day1.close_time,
        daily_minimum=1,
        weekly_minimum=0,
        monthly_minimum=0,
    )
    assert len(bundle.daily.candles) == 1


def test_strategy_bundle_has_no_future_data() -> None:
    candles = make_daily_series(10)
    repo = _repo_with(*candles)
    eval_time = candles[4].close_time
    bundle = get_strategy_bundle(
        repo, MarketSymbol.BTC, eval_time, daily_minimum=1, weekly_minimum=0, monthly_minimum=0
    )
    for series in (bundle.daily, bundle.weekly, bundle.monthly):
        for candle in series.candles:
            assert candle.close_time <= eval_time


def test_weekly_monthly_no_future_in_bundle() -> None:
    monday = weekly_open_containing(dt(2024, 1, 1))
    jan = make_daily_series(31, start=monthly_open(2024, 1))
    repo = _repo_with(*jan)
    eval_time = weekly_close(monday)
    bundle = get_strategy_bundle(
        repo, MarketSymbol.BTC, eval_time, daily_minimum=5, weekly_minimum=1, monthly_minimum=0
    )
    for candle in bundle.weekly.candles:
        assert candle.close_time <= eval_time


def test_reconnect_old_open_candle_not_closed() -> None:
    from market_data.live import LiveFeedProcessor
    from market_data.providers.in_memory import InMemoryLiveProvider
    from market_data.service import MarketDataService

    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 1, 12))
    processor.connect()
    open_day = make_daily(day=dt(2024, 1, 1), is_closed=False)
    from tests.market_data.conftest import to_raw

    live.push(to_raw(open_day))
    processor.process_events(dt(2024, 1, 1, 12))
    stored = repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)
    assert stored[0].is_closed is False
