# ruff: noqa: E402
"""Validation and duplicate handling tests."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from market_data.models import (
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
)
from market_data.repository import InMemoryCandleRepository
from market_data.validation import (
    candles_equal,
    sort_candles,
    validate_series,
    validate_single_candle,
)

from tests.market_data.conftest import dt, make_daily, make_daily_series


def test_valid_historical_series() -> None:
    candles = make_daily_series(5)
    report = validate_series(
        candles, MarketSymbol.BTC, MarketTimeframe.DAILY, candles[-1].close_time
    )
    assert report.status == DataQualityStatus.VALID
    assert MarketDataReasonCode.MD_VALID in report.reason_codes


def test_unsorted_input_flagged() -> None:
    candles = make_daily_series(3)
    unsorted = (candles[2], candles[0], candles[1])
    report = validate_series(
        unsorted, MarketSymbol.BTC, MarketTimeframe.DAILY, candles[-1].close_time
    )
    assert report.status == DataQualityStatus.INVALID


def test_sort_candles_orders_chronologically() -> None:
    candles = make_daily_series(3)
    unsorted = (candles[2], candles[0], candles[1])
    assert [c.open_time for c in sort_candles(unsorted)] == [c.open_time for c in candles]


def test_identical_duplicate_idempotent_in_repository() -> None:
    repo = InMemoryCandleRepository()
    candle = make_daily()
    assert repo.upsert(candle) == (True, None)
    assert repo.upsert(candle) == (False, None)
    assert len(repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)) == 1


def test_conflicting_duplicate_marks_invalid() -> None:
    repo = InMemoryCandleRepository()
    base = make_daily()
    repo.upsert(base)
    conflict = base.model_copy(update={"close": Decimal("200")})
    added, detail = repo.upsert(conflict)
    assert added is False
    assert detail is not None
    report = validate_series(
        repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY),
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        base.close_time,
        conflicts=repo.conflicts,
    )
    assert report.status == DataQualityStatus.INVALID
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT in report.reason_codes


def test_candles_equal_detects_identity() -> None:
    a = make_daily()
    b = a.model_copy()
    assert candles_equal(a, b)


def test_invalid_ohlc_structure() -> None:
    candle = make_daily(h="90", low="95")
    codes = validate_single_candle(candle, candle.close_time)
    assert MarketDataReasonCode.MD_INVALID_OHLC in codes


def test_negative_prices_rejected() -> None:
    candle = make_daily(o="-1")
    codes = validate_single_candle(candle, candle.close_time)
    assert MarketDataReasonCode.MD_INVALID_OHLC in codes


def test_negative_volume_rejected() -> None:
    candle = make_daily(vol="-1")
    codes = validate_single_candle(candle, candle.close_time)
    assert MarketDataReasonCode.MD_INVALID_VOLUME in codes


def test_nan_rejected() -> None:
    candle = make_daily()
    bad = candle.model_copy(update={"close": Decimal("NaN")})
    codes = validate_single_candle(bad, candle.close_time)
    assert MarketDataReasonCode.MD_INVALID_OHLC in codes


def test_infinity_rejected() -> None:
    candle = make_daily()
    bad = candle.model_copy(update={"high": Decimal("Infinity")})
    codes = validate_single_candle(bad, candle.close_time)
    assert MarketDataReasonCode.MD_INVALID_OHLC in codes


def test_open_candle_excluded() -> None:
    candle = make_daily(is_closed=False)
    eval_time = candle.open_time + timedelta(hours=12)
    codes = validate_single_candle(candle, eval_time)
    assert (
        MarketDataReasonCode.MD_FUTURE_CANDLE in codes
        or MarketDataReasonCode.MD_OPEN_CANDLE_EXCLUDED in codes
    )


def test_future_candle_rejected() -> None:
    candle = make_daily(day=dt(2024, 1, 10))
    codes = validate_single_candle(candle, dt(2024, 1, 1))
    assert MarketDataReasonCode.MD_FUTURE_CANDLE in codes


def test_evaluation_exactly_at_close_allowed() -> None:
    candle = make_daily()
    codes = validate_single_candle(candle, candle.close_time)
    assert codes == ()


def test_naive_datetime_rejected_by_ensure_utc() -> None:
    from market_data.timeframes import ensure_utc

    with pytest.raises(ValueError):
        ensure_utc(dt(2024, 1, 1).replace(tzinfo=None))
