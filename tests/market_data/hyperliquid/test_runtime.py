# ruff: noqa: E402
"""Hyperliquid runtime integration tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import ConnectionStatus, MarketSymbol, MarketTimeframe
from market_data.network.errors import HyperliquidWebSocketError
from market_data.network.http_client import HyperliquidHttpClient
from market_data.network.websocket_client import FakeWebSocketConnection
from market_data.providers.hyperliquid_ws import HyperliquidWebSocketFeed
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService

from tests.market_data.hyperliquid.conftest import (
    all_ack_messages,
    candle_dict,
    fixed_clock,
    immediate_sleep,
    meta_response,
)


@pytest.mark.asyncio
async def test_backfill_symbol_uses_ingest_path() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body.get("type") == "meta":
            return httpx.Response(200, json=meta_response())
        return httpx.Response(200, json=[candle_dict()])

    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    http = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
    )
    repo = InMemoryCandleRepository()
    runtime = HyperliquidMarketDataRuntime(MarketDataService(repo), config, http_client=http)
    end = datetime(2024, 1, 2, tzinfo=UTC)
    report = await runtime.backfill_symbol(
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        datetime(2024, 1, 1, tzinfo=UTC),
        end,
        end,
    )
    assert len(repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)) == 1
    assert report.status.value in {"VALID", "INCOMPLETE"}
    await runtime.aclose()


@pytest.mark.asyncio
async def test_hanging_reconnect_timeout_is_retried_on_next_runtime_poll() -> None:
    evaluation_time = datetime(2024, 1, 2, tzinfo=UTC)
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        reconnect_initial_delay_seconds=0.001,
        reconnect_max_delay_seconds=0.01,
        reconnect_total_timeout_seconds=0.01,
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    never_connected = asyncio.Event()
    attempts = 0

    async def connect(_: str) -> FakeWebSocketConnection:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await never_connected.wait()
            raise AssertionError("unreachable")
        for ack in all_ack_messages(config):
            await incoming.put(ack)
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(evaluation_time),
        sleep=immediate_sleep,
    )
    feed._status = ConnectionStatus.RECONNECTING
    runtime = HyperliquidMarketDataRuntime(
        MarketDataService(InMemoryCandleRepository()),
        config,
        ws_feed=feed,
    )

    with pytest.raises(HyperliquidWebSocketError, match="reconnect exceeded"):
        await runtime.process_live(evaluation_time)

    assert feed.status == ConnectionStatus.RECONNECTING

    await runtime.process_live(evaluation_time)

    assert feed.status == ConnectionStatus.CONNECTED
    assert attempts == 2
    await runtime.aclose()
