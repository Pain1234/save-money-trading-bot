# ruff: noqa: E402
"""Live feed, stale detection, reconnect tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from market_data.live import LiveFeedProcessor
from market_data.models import (
    ConnectionStatus,
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
)
from market_data.providers.in_memory import InMemoryLiveProvider
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, to_raw


def test_connect_and_process_event() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    now = dt(2024, 1, 2)
    processor = LiveFeedProcessor(service, live, clock=lambda: now)
    processor.connect()
    candle = make_daily(day=dt(2024, 1, 1))
    live.push(to_raw(candle))
    count = processor.process_events(candle.close_time)
    assert count == 1
    assert processor.status == ConnectionStatus.CONNECTED


def test_stale_detection() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    t0 = dt(2024, 1, 1)
    clock_state = {"now": t0}

    def clock() -> datetime:
        return clock_state["now"]

    processor = LiveFeedProcessor(
        service,
        live,
        stale_threshold_seconds=60,
        clock=clock,
    )
    processor.connect()
    clock_state["now"] = t0 + timedelta(minutes=5)
    health = processor.health(clock_state["now"])
    assert health.stale is True
    assert health.report is not None
    assert health.report.status == DataQualityStatus.STALE


def test_disconnect_status() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 1))
    health = processor.health(dt(2024, 1, 1))
    assert health.report is not None
    assert health.report.status == DataQualityStatus.DISCONNECTED
    assert MarketDataReasonCode.MD_DISCONNECTED in health.report.reason_codes


def test_reconnect_deduplicates_events() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    sleeps: list[float] = []
    processor = LiveFeedProcessor(
        service,
        live,
        clock=lambda: dt(2024, 1, 2),
        sleep=lambda s: sleeps.append(s),
    )
    processor.connect()
    candle = make_daily(day=dt(2024, 1, 1))
    raw = to_raw(candle)
    live.push(raw)
    processor.process_events(candle.close_time)
    live.push(raw)
    processor.reconnect_once(candle.close_time)
    assert len(repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)) == 1
    assert sleeps == [1.0]


def test_graceful_shutdown() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 1))
    processor.connect()
    processor.graceful_shutdown()
    assert processor.status == ConnectionStatus.SHUTDOWN
