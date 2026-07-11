# ruff: noqa: E402
"""Gap detection and backfill tests."""

from __future__ import annotations

from market_data.gaps import detect_gaps
from market_data.models import (
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
)
from market_data.providers.in_memory import InMemoryBackfillProvider
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, make_daily_series, to_raw


def test_missing_candle_detected() -> None:
    candles = make_daily_series(3)
    missing = (candles[0], candles[2])
    gaps = detect_gaps(missing, MarketSymbol.BTC, MarketTimeframe.DAILY, candles[2].close_time)
    assert len(gaps) == 1
    assert gaps[0].missing_open_time == candles[1].open_time


def test_successful_backfill_closes_gap() -> None:
    candles = make_daily_series(3)
    missing = (candles[0], candles[2])
    repo = InMemoryCandleRepository()
    repo.upsert_many(missing)
    backfill_data = {(MarketSymbol.BTC, MarketTimeframe.DAILY): (to_raw(candles[1]),)}
    service = MarketDataService(repo, backfill=InMemoryBackfillProvider(backfill_data))
    report = service.attempt_backfill(
        MarketSymbol.BTC, MarketTimeframe.DAILY, candles[2].close_time
    )
    assert report.status == DataQualityStatus.VALID


def test_failed_backfill_incomplete() -> None:
    candles = make_daily_series(3)
    missing = (candles[0], candles[2])
    repo = InMemoryCandleRepository()
    repo.upsert_many(missing)
    provider = InMemoryBackfillProvider({})
    provider.fail = True
    service = MarketDataService(repo, backfill=provider)
    report = service.attempt_backfill(
        MarketSymbol.BTC, MarketTimeframe.DAILY, candles[2].close_time
    )
    assert report.status == DataQualityStatus.INCOMPLETE
    assert MarketDataReasonCode.MD_BACKFILL_FAILED in report.reason_codes
    assert MarketDataReasonCode.MD_GAP_DETECTED in report.reason_codes


def test_repository_get_closed_before() -> None:
    repo = InMemoryCandleRepository()
    candle = make_daily(day=dt(2024, 1, 1))
    repo.upsert(candle)
    closed = repo.get_closed_before(MarketSymbol.BTC, MarketTimeframe.DAILY, candle.close_time)
    assert len(closed) == 1
    future = repo.get_closed_before(MarketSymbol.BTC, MarketTimeframe.DAILY, dt(2023, 12, 31))
    assert future == ()
