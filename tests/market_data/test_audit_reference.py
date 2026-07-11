# ruff: noqa: E402
"""Independent reference tests with hand-calculated expectations."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from market_data.aggregation import aggregate_monthly_from_daily, aggregate_weekly_from_daily
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.providers.hyperliquid import HyperliquidCandleAdapter
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, make_daily_series


def test_daily_close_boundary_microseconds() -> None:
    repo = InMemoryCandleRepository()
    candle = make_daily(day=dt(2024, 1, 1))
    repo.upsert(candle)
    close = candle.close_time
    assert repo.get_closed_before(MarketSymbol.BTC, MarketTimeframe.DAILY, close - timedelta(microseconds=1)) == ()
    assert len(repo.get_closed_before(MarketSymbol.BTC, MarketTimeframe.DAILY, close)) == 1
    assert len(repo.get_closed_before(MarketSymbol.BTC, MarketTimeframe.DAILY, close + timedelta(microseconds=1))) == 1


def test_no_false_gap_between_day_boundary() -> None:
    from market_data.gaps import detect_gaps

    c1 = make_daily(day=dt(2024, 1, 1))
    c2 = make_daily(day=dt(2024, 1, 2))
    gaps = detect_gaps((c1, c2), MarketSymbol.BTC, MarketTimeframe.DAILY, c2.close_time)
    assert gaps == ()


def test_february_2023_has_28_days_in_monthly_aggregate() -> None:
    dailies = make_daily_series(28, start=dt(2023, 2, 1))
    agg = aggregate_monthly_from_daily(dailies, MarketSymbol.BTC, dailies[-1].close_time)
    assert len(agg) == 1
    assert agg[0].open_time == dt(2023, 2, 1)
    assert agg[0].volume == Decimal("28000")


def test_february_2024_leap_year_has_29_days() -> None:
    dailies = make_daily_series(29, start=dt(2024, 2, 1))
    agg = aggregate_monthly_from_daily(dailies, MarketSymbol.BTC, dailies[-1].close_time)
    assert len(agg) == 1
    assert agg[0].volume == Decimal("29000")


def test_weekly_ohlcv_from_seven_dailies_hand_calculated() -> None:
    dailies = tuple(
        make_daily(
            day=dt(2024, 1, 1) + timedelta(days=i),
            o=str(100 + i),
            h=str(110 + i),
            low=str(90 + i),
            c=str(105 + i),
            vol="10",
        )
        for i in range(7)
    )
    agg = aggregate_weekly_from_daily(dailies, MarketSymbol.BTC, dailies[-1].close_time)
    assert len(agg) == 1
    w = agg[0]
    assert w.open == Decimal("100")
    assert w.high == Decimal("116")
    assert w.low == Decimal("90")
    assert w.close == Decimal("111")
    assert w.volume == Decimal("70")


def test_january_monthly_ohlcv_from_31_dailies() -> None:
    dailies = make_daily_series(31, start=dt(2024, 1, 1))
    agg = aggregate_monthly_from_daily(dailies, MarketSymbol.BTC, dailies[-1].close_time)
    assert len(agg) == 1
    assert agg[0].open == Decimal("100")
    assert agg[0].close == Decimal("100")
    assert agg[0].volume == Decimal("31000")


def test_hyperliquid_epoch_1704067200000() -> None:
    adapter = HyperliquidCandleAdapter()
    payload = {
        "s": "BTC",
        "i": "1d",
        "t": 1704067200000,
        "T": 1704153599000,
        "o": "1",
        "h": "1",
        "l": "1",
        "c": "1",
        "v": "1",
        "closed": True,
    }
    raw = adapter.parse_candle(payload)
    assert raw.open_time == dt(2024, 1, 1)


def test_usable_bundle_no_lookahead_property() -> None:
    dailies = make_daily_series(35, start=dt(2024, 1, 1))
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    service = MarketDataService(repo)
    eval_time = dailies[-1].close_time
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=21,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert bundle.is_usable
    for series in (bundle.daily, bundle.weekly, bundle.monthly):
        for candle in series.candles:
            assert candle.close_time <= eval_time


def test_cross_symbol_conflict_isolation_reference() -> None:
    from decimal import Decimal

    from market_data.models import DataQualityStatus, MarketDataReasonCode

    btc = make_daily_series(35, symbol=MarketSymbol.BTC)
    eth = make_daily(day=dt(2024, 1, 1), symbol=MarketSymbol.ETH)
    repo = InMemoryCandleRepository()
    repo.upsert_many(btc)
    repo.upsert(eth)
    repo.upsert(eth.model_copy(update={"close": Decimal("500")}))
    service = MarketDataService(repo)
    eval_time = btc[-1].close_time
    btc_bundle = service.build_strategy_bundle(
        MarketSymbol.BTC, eval_time, 21, 1, 1, backfill=False
    )
    eth_bundle = service.build_strategy_bundle(
        MarketSymbol.ETH, eval_time, 1, 1, 1, backfill=False
    )
    assert btc_bundle.is_usable
    assert eth_bundle.report.status == DataQualityStatus.INVALID
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT in eth_bundle.report.reason_codes


def test_hand_constructed_full_usable_bundle() -> None:
    dailies = make_daily_series(90, start=dt(2023, 10, 1))
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    service = MarketDataService(repo)
    eval_time = dailies[-1].close_time
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=60,
        weekly_minimum=8,
        monthly_minimum=2,
        backfill=False,
    )
    assert bundle.is_usable
    assert bundle.daily.length == 60
    assert bundle.weekly.length >= 8
    assert bundle.monthly.length >= 2
