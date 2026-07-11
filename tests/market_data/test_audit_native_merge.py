# ruff: noqa: E402
"""C1/C6 regression: native vs aggregated weekly/monthly policy."""

from __future__ import annotations

from decimal import Decimal

from market_data.aggregation import aggregate_weekly_from_daily
from market_data.models import DataQualityStatus, MarketDataReasonCode, MarketSymbol
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily_series, make_monthly, make_weekly


def test_single_native_weekly_supplemented_by_daily_aggregation() -> None:
    dailies = make_daily_series(400, start=dt(2023, 1, 2))
    eval_time = dailies[-1].close_time
    native_weekly = make_weekly(
        monday=dt(2023, 1, 2),
        complete_from_daily=dailies[:7],
    )
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert(native_weekly)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=21,
        weekly_minimum=50,
        monthly_minimum=1,
        backfill=False,
    )
    assert bundle.weekly.length >= 50
    assert bundle.is_usable is True


def test_identical_native_and_aggregated_weekly_no_conflict() -> None:
    dailies = make_daily_series(14, start=dt(2024, 1, 1))
    eval_time = dailies[-1].close_time
    native = make_weekly(monday=dt(2024, 1, 1), complete_from_daily=dailies[:7])
    aggregated = aggregate_weekly_from_daily(dailies, MarketSymbol.BTC, eval_time)
    assert any(a.open_time == native.open_time for a in aggregated)
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert(native)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=7,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT not in bundle.report.reason_codes


def test_conflicting_native_and_aggregated_weekly_invalidates_bundle() -> None:
    dailies = make_daily_series(14, start=dt(2024, 1, 1))
    eval_time = dailies[-1].close_time
    native = make_weekly(
        monday=dt(2024, 1, 1), complete_from_daily=dailies[:7]
    ).model_copy(update={"close": Decimal("999"), "high": Decimal("999")})
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert(native)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=7,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert bundle.report.status == DataQualityStatus.INVALID
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT in bundle.report.reason_codes


def test_identical_native_and_aggregated_monthly_no_conflict() -> None:
    dailies = make_daily_series(31, start=dt(2024, 1, 1))
    eval_time = dailies[-1].close_time
    native = make_monthly(year=2024, month=1, complete_from_daily=dailies)
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert(native)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=21,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT not in bundle.report.reason_codes


def test_conflicting_native_and_aggregated_monthly_invalidates_bundle() -> None:
    dailies = make_daily_series(31, start=dt(2024, 1, 1))
    eval_time = dailies[-1].close_time
    native = make_monthly(
        year=2024, month=1, complete_from_daily=dailies
    ).model_copy(update={"close": Decimal("999")})
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert(native)
    service = MarketDataService(repo)
    bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=21,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    assert bundle.report.status == DataQualityStatus.INVALID
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT in bundle.report.reason_codes
