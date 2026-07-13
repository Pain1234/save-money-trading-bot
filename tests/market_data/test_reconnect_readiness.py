"""Reconnect diagnostics, open-candle merge, and readiness recovery."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import ConnectionStatus, MarketSymbol, MarketTimeframe
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily_series, make_monthly, make_weekly, to_raw


def _connect_transport(runtime: HyperliquidMarketDataRuntime) -> None:
    runtime._ws._status = ConnectionStatus.CONNECTED  # noqa: SLF001
    runtime._ws._acked_subs = set(runtime._ws._expected_subs)  # noqa: SLF001


@pytest.mark.asyncio
async def test_reconnect_backfill_replaces_open_candle_without_conflict() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.MONTHLY,),
    )
    repo = InMemoryCandleRepository()
    existing = make_monthly(MarketSymbol.BTC, 2026, 7).model_copy(
        update={"is_closed": False}
    )
    updated = existing.model_copy(
        update={
            "high": Decimal("112"),
            "close": Decimal("106"),
            "is_closed": False,
        }
    )
    repo.upsert(existing)
    runtime = HyperliquidMarketDataRuntime(MarketDataService(repo), config)
    runtime._http.post_info = AsyncMock(  # type: ignore[method-assign]
        return_value={"universe": [{"name": "BTC"}]}
    )
    runtime._historical.fetch_candles = AsyncMock(  # type: ignore[method-assign]
        return_value=(to_raw(updated),)
    )
    evaluation_time = dt(2026, 7, 13, 12)

    await runtime.backfill_symbol(
        MarketSymbol.BTC,
        MarketTimeframe.MONTHLY,
        existing.open_time,
        evaluation_time,
        evaluation_time,
    )

    assert repo.conflicts == ()
    assert repo.get_latest(MarketSymbol.BTC, MarketTimeframe.MONTHLY) == updated


@pytest.mark.asyncio
async def test_transport_reconnect_without_strategy_readiness_is_degraded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logging.getLogger("market_data.runtime").disabled = False
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )
    runtime = HyperliquidMarketDataRuntime(
        MarketDataService(InMemoryCandleRepository()),
        config,
    )
    runtime._meta_ok = True  # noqa: SLF001
    runtime._backfill_ok = True  # noqa: SLF001
    runtime._initial_backfill_done = True  # noqa: SLF001
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001
    runtime._ws.reconnect = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda: _connect_transport(runtime)
    )
    runtime._ws.end_buffer = lambda: ()  # type: ignore[method-assign]
    evaluation_time = dt(2026, 7, 13, 12)

    with caplog.at_level(logging.INFO):
        await runtime.reconnect(evaluation_time)

    messages = [record.getMessage() for record in caplog.records]
    assert "market_data_transport_reconnect_succeeded" in messages
    assert any(message.startswith("market_data_reconnect_degraded") for message in messages)
    assert runtime.status(evaluation_time).readiness is False


def _seed_ready_history(repo: InMemoryCandleRepository):
    daily_start = dt(2023, 1, 16)
    dailies = make_daily_series(364, start=daily_start, symbol=MarketSymbol.BTC)
    weeklies = tuple(
        make_weekly(MarketSymbol.BTC, daily_start + timedelta(weeks=index))
        for index in range(52)
    )
    monthlies = []
    year, month = 2022, 5
    for _ in range(20):
        monthlies.append(make_monthly(MarketSymbol.BTC, year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    repo.upsert_many(dailies)
    repo.upsert_many(weeklies)
    repo.upsert_many(tuple(monthlies))
    return dailies[-1].close_time + timedelta(hours=1)


@pytest.mark.asyncio
async def test_reconnect_logs_readiness_recovered_and_returns_ready(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logging.getLogger("market_data.runtime").disabled = False
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
    )
    repo = InMemoryCandleRepository()
    evaluation_time = _seed_ready_history(repo)
    runtime = HyperliquidMarketDataRuntime(MarketDataService(repo), config)
    runtime._meta_ok = True  # noqa: SLF001
    runtime._backfill_ok = True  # noqa: SLF001
    runtime._initial_backfill_done = True  # noqa: SLF001
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001
    runtime._ws.reconnect = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda: _connect_transport(runtime)
    )
    runtime._ws.end_buffer = lambda: ()  # type: ignore[method-assign]
    runtime.backfill_symbol = AsyncMock()  # type: ignore[method-assign]

    with caplog.at_level(logging.INFO):
        await runtime.reconnect(evaluation_time)

    assert "market_data_readiness_recovered" in {
        record.getMessage() for record in caplog.records
    }
    assert runtime.status(evaluation_time).readiness is True
