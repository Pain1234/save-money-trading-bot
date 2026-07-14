# ruff: noqa: E402
"""Hyperliquid WebSocket tests — no real network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.ingest import ingest_live_raw
from market_data.models import ConnectionStatus, MarketSymbol, MarketTimeframe
from market_data.network.errors import HyperliquidWebSocketError
from market_data.network.websocket_client import FakeWebSocketConnection
from market_data.providers.hyperliquid import HyperliquidCandleAdapter
from market_data.providers.hyperliquid_ws import HyperliquidWebSocketFeed
from market_data.repository import InMemoryCandleRepository

from tests.market_data.hyperliquid.conftest import (
    all_ack_messages,
    candle_dict,
    fixed_clock,
    immediate_sleep,
)


@pytest.mark.asyncio
async def test_provider_subscriptions_exclude_non_iso_weekly_streams() -> None:
    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    outgoing: list[str] = []
    for ack in all_ack_messages(config):
        await incoming.put(ack)

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=outgoing)

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    await feed.connect_and_subscribe()
    assert len(outgoing) == 6
    assert feed.subscriptions_acknowledged == 6
    assert all('"interval":"1w"' not in message for message in outgoing)
    await feed.disconnect()


@pytest.mark.asyncio
async def test_missing_ack_timeout() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET, subscription_ack_timeout_seconds=0.01
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    with pytest.raises(HyperliquidWebSocketError, match="acknowledgement timeout"):
        await feed.connect_and_subscribe()
    await feed.disconnect()


@pytest.mark.asyncio
async def test_open_candle_update_allowed() -> None:
    repo = InMemoryCandleRepository()
    eval_time = datetime(2024, 1, 1, 12, tzinfo=UTC)
    adapter = HyperliquidCandleAdapter()
    open_ms = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    close_ms = int(datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC).timestamp() * 1000)
    raw1 = adapter.parse_candle(
        candle_dict(t=open_ms, big_t=close_ms, c="100"),
        strict=True,
        evaluation_time=eval_time,
    )
    raw2 = adapter.parse_candle(
        candle_dict(t=open_ms, big_t=close_ms, c="101", h="111"),
        strict=True,
        evaluation_time=eval_time,
    )
    ingest_live_raw(repo, (raw1,), eval_time)
    result = ingest_live_raw(repo, (raw2,), eval_time)
    assert result.inserted == 1
    assert len(repo.conflicts) == 0
    stored = repo.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)
    assert stored[0].close == Decimal("101")


@pytest.mark.asyncio
async def test_failed_reconnect_remains_retryable_with_exponential_backoff() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        reconnect_initial_delay_seconds=0.25,
        reconnect_max_delay_seconds=10.0,
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    for ack in all_ack_messages(config):
        await incoming.put(ack)

    attempts = 0
    delays: list[float] = []

    async def connect(_: str) -> FakeWebSocketConnection:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("server rejected WebSocket connection: HTTP 502")
        return FakeWebSocketConnection(incoming, outgoing=[])

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=record_sleep,
    )

    with pytest.raises(RuntimeError, match="HTTP 502"):
        await feed.reconnect()

    assert feed.status == ConnectionStatus.RECONNECTING
    assert feed.background_error == "server rejected WebSocket connection: HTTP 502"

    await feed.reconnect()

    assert feed.status == ConnectionStatus.CONNECTED
    assert attempts == 2
    assert delays == [0.25, 0.5]
    await feed.disconnect()


@pytest.mark.asyncio
async def test_shutdown_status() -> None:
    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    for ack in all_ack_messages(config):
        await incoming.put(ack)

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    await feed.connect_and_subscribe()
    await feed.disconnect()
    assert feed.status == ConnectionStatus.SHUTDOWN
