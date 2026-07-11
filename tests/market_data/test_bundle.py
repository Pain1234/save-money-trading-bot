# ruff: noqa: E402
"""Strategy bundle tests."""

from __future__ import annotations

from market_data.models import DataQualityStatus, MarketSymbol
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import make_daily_series


def test_strategy_bundle_valid_when_complete() -> None:
    dailies = make_daily_series(25)
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        dailies[-1].close_time,
        daily_minimum=21,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert bundle.daily.length >= 21
    assert bundle.symbol == MarketSymbol.BTC


def test_strategy_bundle_incomplete_when_history_short() -> None:
    dailies = make_daily_series(5)
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        dailies[-1].close_time,
        daily_minimum=21,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert bundle.report.status == DataQualityStatus.INCOMPLETE
    assert bundle.is_usable is False


def test_deterministic_repeatable_bundle() -> None:
    dailies = make_daily_series(30)
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    service = MarketDataService(repo)
    eval_time = dailies[-1].close_time
    b1 = service.build_strategy_bundle(
        MarketSymbol.BTC, eval_time, 21, 1, 1, backfill=False
    )
    b2 = service.build_strategy_bundle(
        MarketSymbol.BTC, eval_time, 21, 1, 1, backfill=False
    )
    assert b1.daily.candles == b2.daily.candles
    assert b1.report.status == b2.report.status
