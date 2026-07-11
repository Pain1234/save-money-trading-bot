# ruff: noqa: E402
"""Medium audit fixes M1-M10."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from market_data.live import LiveFeedProcessor
from market_data.models import (
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
)
from market_data.providers.hyperliquid import HyperliquidCandleAdapter
from market_data.providers.in_memory import InMemoryBackfillProvider
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService
from market_data.stale import is_candle_data_stale
from market_data.validation import validate_candle_structure, validate_series

from tests.market_data.conftest import dt, make_daily, make_daily_series, to_raw


def test_transport_stale_separate_from_candle_stale() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    from market_data.providers.in_memory import InMemoryLiveProvider

    live = InMemoryLiveProvider()
    t0 = dt(2024, 1, 1, 12)
    clock_state = {"now": t0}
    processor = LiveFeedProcessor(
        service,
        live,
        stale_threshold_seconds=3600,
        clock=lambda: clock_state["now"],
    )
    processor.connect()
    candle = make_daily(day=dt(2024, 1, 1))
    live.push(to_raw(candle))
    processor.process_events(candle.close_time)
    clock_state["now"] = t0 + timedelta(minutes=30)
    assert processor.is_transport_stale(clock_state["now"]) is False
    assert processor.is_stale(clock_state["now"]) is False


def test_candle_stale_after_expected_close_without_update() -> None:
    candle = make_daily(day=dt(2024, 1, 1))
    eval_before = dt(2024, 1, 1, 12)
    assert is_candle_data_stale(candle, eval_before) is False
    eval_after = dt(2024, 1, 3, 1)
    assert is_candle_data_stale(candle, eval_after) is True


def test_failed_backfill_keeps_gap_detected() -> None:
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
    assert MarketDataReasonCode.MD_GAP_DETECTED in report.reason_codes
    assert MarketDataReasonCode.MD_BACKFILL_FAILED in report.reason_codes


def test_backfill_respects_symbol_and_timeframe() -> None:
    candles = make_daily_series(3)
    missing = (candles[0], candles[2])
    repo = InMemoryCandleRepository()
    repo.upsert_many(missing)
    eth_candle = make_daily(day=candles[1].open_time, symbol=MarketSymbol.ETH)
    backfill_data = {
        (MarketSymbol.BTC, MarketTimeframe.DAILY): (to_raw(candles[1]),),
        (MarketSymbol.ETH, MarketTimeframe.DAILY): (to_raw(eth_candle),),
    }
    service = MarketDataService(repo, backfill=InMemoryBackfillProvider(backfill_data))
    report = service.attempt_backfill(
        MarketSymbol.BTC, MarketTimeframe.DAILY, candles[2].close_time
    )
    assert report.status == DataQualityStatus.VALID
    assert len(repo.get_range(MarketSymbol.ETH, MarketTimeframe.DAILY)) == 0


def test_overlapping_intervals_rejected() -> None:
    c1 = make_daily(day=dt(2024, 1, 1))
    c2 = make_daily(day=dt(2024, 1, 1))
    c2_overlap = c2.model_copy(
        update={
            "open_time": dt(2024, 1, 1, 12),
            "close_time": datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        }
    )
    report = validate_series(
        (c1, c2_overlap),
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        dt(2024, 1, 2),
    )
    assert MarketDataReasonCode.MD_INVALID in report.reason_codes


def test_non_finite_volume_uses_invalid_volume_code() -> None:
    candle = make_daily(day=dt(2024, 1, 1)).model_copy(update={"volume": Decimal("NaN")})
    codes = validate_candle_structure(candle)
    assert MarketDataReasonCode.MD_INVALID_VOLUME in codes
    assert MarketDataReasonCode.MD_INVALID_OHLC not in codes


def test_hyperliquid_rejects_missing_closed_default_open() -> None:
    adapter = HyperliquidCandleAdapter()
    payload = {
        "s": "BTC",
        "i": "1d",
        "t": 1704067200000,
        "T": 1704153599000,
        "o": "42000",
        "h": "43000",
        "l": "41000",
        "c": "42500",
        "v": "1234.5",
    }
    raw = adapter.parse_candle(payload)
    assert raw.is_closed is False


def test_hyperliquid_rejects_nan_string() -> None:
    adapter = HyperliquidCandleAdapter()
    payload = {
        "s": "BTC",
        "i": "1d",
        "t": 1704067200000,
        "T": 1704153599000,
        "o": "NaN",
        "h": "43000",
        "l": "41000",
        "c": "42500",
        "v": "1234.5",
    }
    with pytest.raises(ValueError, match="Non-finite"):
        adapter.parse_candle(payload)


def test_reconnect_backfills_all_timeframes_and_resets_backoff() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    from market_data.providers.in_memory import InMemoryLiveProvider

    live = InMemoryLiveProvider()
    sleeps: list[float] = []
    processor = LiveFeedProcessor(
        service,
        live,
        clock=lambda: dt(2024, 2, 1),
        sleep=lambda s: sleeps.append(s),
    )
    processor.connect()
    processor._backoff_attempts = 2
    processor.reconnect_once(dt(2024, 2, 1))
    assert processor._backoff_attempts == 0
    assert sleeps == [4.0]


def test_shutdown_prevents_processing() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    from market_data.providers.in_memory import InMemoryLiveProvider

    live = InMemoryLiveProvider()
    processor = LiveFeedProcessor(service, live, clock=lambda: dt(2024, 1, 2))
    processor.connect()
    processor.graceful_shutdown()
    live.push(to_raw(make_daily(day=dt(2024, 1, 1))))
    assert processor.process_events(dt(2024, 1, 2)) == 0


def test_duplicate_identical_emitted_on_reingest() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    candle = make_daily(day=dt(2024, 1, 1))
    first = service.store_normalized((candle,), candle.close_time)
    assert first.inserted == 1
    second = service.store_normalized((candle,), candle.close_time)
    assert second.identical_skipped == 1
    assert MarketDataReasonCode.MD_DUPLICATE_IDENTICAL in second.reason_codes
