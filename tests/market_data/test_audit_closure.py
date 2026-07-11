# ruff: noqa: E402
"""C2 regression: query-time closure ignores stale is_closed flag."""

from __future__ import annotations

from datetime import timedelta

from market_data.models import MarketSymbol, MarketTimeframe
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, to_raw


def test_open_candle_becomes_closed_at_later_evaluation_time() -> None:
    candle = make_daily(day=dt(2024, 1, 1), is_closed=False)
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    ingest_time = dt(2024, 1, 1, 12)
    service.ingest_raw((to_raw(candle),), ingest_time)

    before_close = candle.close_time.replace(microsecond=0) - timedelta(seconds=1)
    assert repo.get_closed_before(
        MarketSymbol.BTC, MarketTimeframe.DAILY, before_close
    ) == ()

    at_close = candle.close_time
    closed = repo.get_closed_before(
        MarketSymbol.BTC, MarketTimeframe.DAILY, at_close
    )
    assert len(closed) == 1
    assert closed[0].open_time == candle.open_time

    after_close = candle.close_time + timedelta(hours=1)
    assert len(
        repo.get_closed_before(
            MarketSymbol.BTC, MarketTimeframe.DAILY, after_close
        )
    ) == 1
