# ruff: noqa: E402
"""Initial backfill window and native strategy bundle readiness tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.initial_backfill import (
    MINIMUM_INITIAL_BACKFILL_DAYS,
    compute_initial_backfill_start,
    evaluate_native_strategy_bundle_readiness,
    format_initial_backfill_log,
)
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService
from pydantic import ValidationError
from strategy_engine.constants import (
    MIN_MONTHLY_CANDLES,
)

from tests.market_data.conftest import dt, make_daily, make_daily_series, make_monthly, make_weekly


def utc_dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return dt(year, month, day, hour)


def _monthly_series(count: int, *, start_year: int = 2022, start_month: int = 6) -> tuple:
    monthlies = []
    year = start_year
    month = start_month
    for _ in range(count):
        monthlies.append(make_monthly(MarketSymbol.BTC, year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return tuple(monthlies)


def _seed_native_bundle_history(
    repo: InMemoryCandleRepository,
    *,
    daily_count: int,
    weekly_count: int,
    monthly_count: int,
    symbol: MarketSymbol = MarketSymbol.BTC,
) -> datetime:
    daily_start = utc_dt(2023, 1, 16)
    dailies = make_daily_series(daily_count, start=daily_start, symbol=symbol)
    weeklies = tuple(
        make_weekly(symbol, daily_start + timedelta(weeks=index)) for index in range(weekly_count)
    )
    monthlies = _monthly_series(monthly_count, start_year=2022, start_month=5)
    repo.upsert_many(dailies)
    repo.upsert_many(weeklies)
    repo.upsert_many(monthlies)
    return dailies[-1].close_time + timedelta(hours=1)


def test_compute_initial_backfill_start_uses_timedelta_not_year_replace() -> None:
    evaluation_time = datetime(2024, 2, 29, 12, 0, tzinfo=UTC)
    start = compute_initial_backfill_start(evaluation_time, 730)
    assert start == evaluation_time - timedelta(days=730)


def test_compute_initial_backfill_start_rejects_shorter_window() -> None:
    with pytest.raises(ValueError, match="730"):
        compute_initial_backfill_start(datetime(2024, 6, 1, tzinfo=UTC), 365)


def test_config_rejects_initial_backfill_shorter_than_730_days() -> None:
    with pytest.raises(ValidationError):
        HyperliquidPublicConfig(initial_backfill_days=729)


def test_config_env_override_parses_initial_backfill_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPERLIQUID_INITIAL_BACKFILL_DAYS", "730")
    config = HyperliquidPublicConfig.from_env()
    assert config.initial_backfill_days == 730


def test_twenty_monthly_candles_make_native_bundle_usable() -> None:
    repo = InMemoryCandleRepository()
    evaluation_time = _seed_native_bundle_history(
        repo,
        daily_count=364,
        weekly_count=51,
        monthly_count=MIN_MONTHLY_CANDLES,
    )
    snapshot = evaluate_native_strategy_bundle_readiness(
        repo,
        (MarketSymbol.BTC,),
        evaluation_time,
    )[0]
    assert snapshot.bundle_usable is True
    assert snapshot.market_data_ready is True
    assert "bundle_usable=yes" in format_initial_backfill_log(snapshot)


def test_insufficient_monthly_candles_fail_closed() -> None:
    repo = InMemoryCandleRepository()
    evaluation_time = _seed_native_bundle_history(
        repo,
        daily_count=364,
        weekly_count=51,
        monthly_count=11,
    )
    snapshot = evaluate_native_strategy_bundle_readiness(
        repo,
        (MarketSymbol.BTC,),
        evaluation_time,
    )[0]
    assert snapshot.bundle_usable is False
    assert snapshot.market_data_ready is False
    assert "initial_backfill_insufficient" in format_initial_backfill_log(snapshot)
    assert f"monthly_candles=11/{MIN_MONTHLY_CANDLES}" in format_initial_backfill_log(snapshot)


@pytest.mark.asyncio
async def test_empty_repository_initial_backfill_uses_730_days() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        initial_backfill_days=730,
    )
    runtime = HyperliquidMarketDataRuntime(MarketDataService(InMemoryCandleRepository()), config)
    evaluation_time = datetime(2026, 7, 12, 12, tzinfo=UTC)
    calls: list[tuple[datetime, datetime]] = []

    async def _capture_backfill(
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        evaluation: datetime,
    ):
        calls.append((start_time, end_time))
        from market_data.models import DataQualityReport, DataQualityStatus

        runtime._meta_ok = True  # noqa: SLF001
        runtime._record_backfill_success(evaluation)
        return DataQualityReport(
            status=DataQualityStatus.VALID,
            reason_codes=(),
            gaps=(),
            conflicts=(),
            missing_ranges=(),
            last_known_candle=None,
            expected_next_open=None,
            evaluation_time=evaluation,
            messages=(),
        )

    runtime.backfill_symbol = _capture_backfill  # type: ignore[method-assign]
    runtime._ws.connect_and_subscribe = AsyncMock()  # type: ignore[method-assign]
    runtime._ws.end_buffer = lambda: []  # type: ignore[method-assign]
    runtime._refresh_strategy_bundle_readiness = lambda _: None  # type: ignore[method-assign]
    runtime._http.post_info = AsyncMock(return_value={"universe": [{"name": "BTC"}]})  # type: ignore[method-assign]

    await runtime.start(evaluation_time)

    assert len(calls) == 1
    start_time, end_time = calls[0]
    assert end_time == evaluation_time
    assert start_time == evaluation_time - timedelta(days=730)


@pytest.mark.asyncio
async def test_existing_history_uses_latest_open_time_not_full_backfill() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        initial_backfill_days=730,
    )
    repo = InMemoryCandleRepository()
    latest = make_daily(MarketSymbol.BTC, dt(2026, 1, 1))
    repo.upsert(latest)
    runtime = HyperliquidMarketDataRuntime(MarketDataService(repo), config)
    evaluation_time = datetime(2026, 7, 12, 12, tzinfo=UTC)
    captured_starts: list[datetime] = []

    async def _capture_backfill(
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        evaluation: datetime,
    ):
        captured_starts.append(start_time)
        from market_data.models import DataQualityReport, DataQualityStatus

        runtime._meta_ok = True  # noqa: SLF001
        runtime._record_backfill_success(evaluation)
        return DataQualityReport(
            status=DataQualityStatus.VALID,
            reason_codes=(),
            gaps=(),
            conflicts=(),
            missing_ranges=(),
            last_known_candle=None,
            expected_next_open=None,
            evaluation_time=evaluation,
            messages=(),
        )

    runtime.backfill_symbol = _capture_backfill  # type: ignore[method-assign]
    runtime._ws.connect_and_subscribe = AsyncMock()  # type: ignore[method-assign]
    runtime._ws.end_buffer = lambda: []  # type: ignore[method-assign]
    runtime._refresh_strategy_bundle_readiness = lambda _: None  # type: ignore[method-assign]
    runtime._http.post_info = AsyncMock(return_value={"universe": [{"name": "BTC"}]})  # type: ignore[method-assign]

    await runtime.start(evaluation_time)

    assert captured_starts == [latest.open_time]


@pytest.mark.asyncio
async def test_reconnect_does_not_reload_two_years() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        initial_backfill_days=730,
    )
    repo = InMemoryCandleRepository()
    latest = make_daily(MarketSymbol.BTC, dt(2026, 1, 1))
    repo.upsert(latest)
    runtime = HyperliquidMarketDataRuntime(MarketDataService(repo), config)
    evaluation_time = datetime(2026, 7, 12, 12, tzinfo=UTC)
    captured_starts: list[datetime] = []

    async def _capture_backfill(
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        evaluation: datetime,
    ):
        captured_starts.append(start_time)
        from market_data.models import DataQualityReport, DataQualityStatus

        runtime._record_backfill_success(evaluation)
        return DataQualityReport(
            status=DataQualityStatus.VALID,
            reason_codes=(),
            gaps=(),
            conflicts=(),
            missing_ranges=(),
            last_known_candle=None,
            expected_next_open=None,
            evaluation_time=evaluation,
            messages=(),
        )

    runtime.backfill_symbol = _capture_backfill  # type: ignore[method-assign]
    runtime._ws.reconnect = AsyncMock()  # type: ignore[method-assign]
    runtime._ws.end_buffer = lambda: []  # type: ignore[method-assign]
    runtime._refresh_strategy_bundle_readiness = lambda _: None  # type: ignore[method-assign]

    await runtime.reconnect(evaluation_time)

    assert captured_starts == [latest.open_time]
    assert all(start != evaluation_time - timedelta(days=730) for start in captured_starts)


def test_runtime_readiness_false_when_monthly_history_insufficient() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY, MarketTimeframe.WEEKLY, MarketTimeframe.MONTHLY),
    )
    repo = InMemoryCandleRepository()
    evaluation_time = _seed_native_bundle_history(
        repo,
        daily_count=364,
        weekly_count=51,
        monthly_count=11,
    )
    runtime = HyperliquidMarketDataRuntime(MarketDataService(repo), config)
    runtime._meta_ok = True  # noqa: SLF001
    runtime._backfill_ok = True  # noqa: SLF001
    runtime._initial_backfill_done = True  # noqa: SLF001
    runtime._refresh_strategy_bundle_readiness(evaluation_time)
    status = runtime.status(evaluation_time)
    assert status.readiness is False


def test_default_initial_backfill_days_is_730() -> None:
    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    assert config.initial_backfill_days == MINIMUM_INITIAL_BACKFILL_DAYS
