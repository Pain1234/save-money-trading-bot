# ruff: noqa: E402
"""C5 regression: live dedup with conflict detection."""

from __future__ import annotations

from decimal import Decimal

from market_data.live import LiveFeedProcessor
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.providers.in_memory import InMemoryLiveProvider
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, to_raw


def test_identical_live_replay_is_idempotent() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 2))
    processor.connect()
    candle = make_daily(day=dt(2024, 1, 1))
    raw = to_raw(candle)
    live.push(raw)
    assert processor.process_events(candle.close_time) == 1
    live.push(raw)
    assert processor.process_events(candle.close_time) == 0
    assert len(repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)) == 1


def test_conflicting_live_replay_records_conflict_without_overwrite() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 2))
    processor.connect()
    candle = make_daily(day=dt(2024, 1, 1), c="100")
    raw = to_raw(candle)
    live.push(raw)
    processor.process_events(candle.close_time)
    conflicting = to_raw(
        candle.model_copy(update={"close": Decimal("102"), "high": Decimal("105")})
    )
    live.push(conflicting)
    processor.process_events(candle.close_time)
    stored = repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)
    assert len(stored) == 1
    assert stored[0].close == Decimal("100")
    assert len(repo.conflicts) == 1


def test_invalid_live_payload_not_stored() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 2))
    processor.connect()
    candle = make_daily(day=dt(2024, 1, 1))
    raw = to_raw(candle).model_copy(update={"volume": Decimal("NaN")})
    live.push(raw)
    assert processor.process_events(candle.close_time) == 0
    assert repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY) == ()
