"""Reconnect diagnostics, open-candle merge, and readiness recovery."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from market_data.aggregation import aggregate_weekly_from_daily
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import ConnectionStatus, MarketSymbol, MarketTimeframe
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily_series, make_monthly, to_raw

RUNTIME_LOGGER = "market_data.runtime"


def _log_messages(mock_logger: object) -> list[str]:
    return [str(call.args[0]) for call in mock_logger.call_args_list if call.args]  # type: ignore[attr-defined]


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
async def test_transport_reconnect_without_strategy_readiness_is_degraded() -> None:
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

    runtime_logger = logging.getLogger(RUNTIME_LOGGER)
    with (
        patch.object(runtime_logger, "info") as log_info,
        patch.object(runtime_logger, "warning") as log_warning,
    ):
        await runtime.reconnect(evaluation_time)

    info_messages = _log_messages(log_info)
    warning_messages = _log_messages(log_warning)
    assert "market_data_transport_reconnect_succeeded" in info_messages
    assert any(
        message.startswith("market_data_reconnect_degraded") for message in warning_messages
    )
    assert runtime.status(evaluation_time).readiness is False


def _seed_ready_history(repo: InMemoryCandleRepository):
    daily_start = dt(2023, 1, 16)
    dailies = make_daily_series(364, start=daily_start, symbol=MarketSymbol.BTC)
    evaluation_time = dailies[-1].close_time + timedelta(hours=1)
    weeklies = aggregate_weekly_from_daily(
        dailies,
        MarketSymbol.BTC,
        evaluation_time,
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
    return evaluation_time


@pytest.mark.asyncio
async def test_reconnect_logs_readiness_recovered_and_returns_ready() -> None:
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

    with patch.object(logging.getLogger(RUNTIME_LOGGER), "info") as log_info:
        await runtime.reconnect(evaluation_time)

    assert "market_data_readiness_recovered" in set(_log_messages(log_info))
    assert runtime.status(evaluation_time).readiness is True
