# ruff: noqa: E402
"""C4 regression: validate before persist on all ingest paths."""

from __future__ import annotations

from decimal import Decimal

from market_data.models import MarketDataReasonCode, MarketSymbol, MarketTimeframe
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, to_raw


def test_store_normalized_rejects_invalid_ohlc() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    bad = make_daily(day=dt(2024, 1, 1)).model_copy(
        update={"high": Decimal("50"), "low": Decimal("99")}
    )
    result = service.store_normalized((bad,))
    assert result.inserted == 0
    assert repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY) == ()


def test_ingest_raw_rejects_nan_and_infinity() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    candle = make_daily(day=dt(2024, 1, 1))
    raw_nan = to_raw(candle).model_copy(update={"open": Decimal("NaN")})
    inserted, report = service.ingest_raw((raw_nan,), dt(2024, 1, 2))
    assert inserted == 0
    assert report is not None
    assert MarketDataReasonCode.MD_INVALID_OHLC in report.reason_codes
    assert repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY) == ()

    raw_inf = to_raw(candle).model_copy(update={"close": Decimal("Infinity")})
    inserted2, report2 = service.ingest_raw((raw_inf,), dt(2024, 1, 2))
    assert inserted2 == 0
    assert report2 is not None
    assert MarketDataReasonCode.MD_INVALID_OHLC in report2.reason_codes


def test_ingest_rejects_negative_volume() -> None:
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    candle = make_daily(day=dt(2024, 1, 1))
    raw = to_raw(candle).model_copy(update={"volume": Decimal("-1")})
    inserted, report = service.ingest_raw((raw,), dt(2024, 1, 2))
    assert inserted == 0
    assert report is not None
    assert MarketDataReasonCode.MD_INVALID_VOLUME in report.reason_codes
    assert repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY) == ()
