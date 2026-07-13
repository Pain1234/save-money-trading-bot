# ruff: noqa: E402
"""Regression tests for Hyperliquid reconnect lock deadlock and transport errors."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import ConnectionStatus, DataQualityReport, DataQualityStatus
from market_data.network.errors import HyperliquidWebSocketError
from market_data.network.websocket_client import (
    FakeWebSocketConnection,
    wrap_websocket_transport_error,
)
from market_data.providers.hyperliquid_ws import HyperliquidWebSocketFeed
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService

from tests.market_data.hyperliquid.conftest import (
    all_ack_messages,
    fixed_clock,
    immediate_sleep,
)


class ConnectionClosedOK(Exception):
    """Minimal stand-in for websockets.exceptions.ConnectionClosedOK."""


def _eval_time() -> datetime:
    return datetime(2024, 1, 2, tzinfo=UTC)


def _runtime(
    *,
    reconnect_total_timeout_seconds: float = 5.0,
) -> HyperliquidMarketDataRuntime:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        reconnect_total_timeout_seconds=reconnect_total_timeout_seconds,
        reconnect_initial_delay_seconds=0.001,
    )
    repo = InMemoryCandleRepository()
    return HyperliquidMarketDataRuntime(MarketDataService(repo), config)


def _mark_ready(runtime: HyperliquidMarketDataRuntime) -> None:
    runtime._meta_ok = True  # noqa: SLF001
    runtime._backfill_ok = True  # noqa: SLF001
    runtime._initial_backfill_done = True  # noqa: SLF001
    runtime._strategy_bundles_ready = True  # noqa: SLF001


def _mark_transport_connected(runtime: HyperliquidMarketDataRuntime) -> None:
    runtime._ws._status = ConnectionStatus.CONNECTED  # noqa: SLF001
    runtime._ws._acked_subs = set(runtime._ws._expected_subs)  # noqa: SLF001


async def _noop_backfill(*_args: object, **_kwargs: object) -> DataQualityReport:
    return DataQualityReport(
        status=DataQualityStatus.VALID,
        evaluation_time=_eval_time(),
    )


@pytest.mark.asyncio
async def test_ensure_connected_reconnects_without_deadlock() -> None:
    runtime = _runtime()
    _mark_ready(runtime)
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001

    async def ws_reconnect() -> None:
        await asyncio.sleep(0.02)
        _mark_transport_connected(runtime)

    runtime._ws.reconnect = ws_reconnect  # type: ignore[method-assign]
    with patch.object(runtime, "backfill_symbol", side_effect=_noop_backfill):
        await asyncio.wait_for(runtime._ensure_connected(_eval_time()), timeout=1.0)

    assert runtime._ws.status == ConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_concurrent_process_live_runs_single_reconnect() -> None:
    runtime = _runtime()
    _mark_ready(runtime)
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001
    reconnect_calls = 0

    async def ws_reconnect() -> None:
        nonlocal reconnect_calls
        reconnect_calls += 1
        await asyncio.sleep(0.1)
        _mark_transport_connected(runtime)

    runtime._ws.reconnect = ws_reconnect  # type: ignore[method-assign]
    runtime._ws.drain_events = AsyncMock(return_value=())  # type: ignore[method-assign]

    backfill_calls: list[tuple[object, ...]] = []

    async def counting_backfill(*args: object, **kwargs: object) -> DataQualityReport:
        backfill_calls.append(args)
        return await _noop_backfill(*args, **kwargs)

    with patch.object(runtime, "backfill_symbol", side_effect=counting_backfill):
        await asyncio.wait_for(
            asyncio.gather(
                runtime.process_live(_eval_time()),
                runtime.process_live(_eval_time()),
            ),
            timeout=2.0,
        )

    assert reconnect_calls == 1
    assert len(backfill_calls) <= len(list(runtime._config.symbols)) * len(  # noqa: SLF001
        list(runtime._config.timeframes)
    )


@pytest.mark.asyncio
async def test_second_reconnect_caller_waits_and_returns_after_first() -> None:
    runtime = _runtime()
    _mark_ready(runtime)
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001
    started = asyncio.Event()
    release = asyncio.Event()

    async def ws_reconnect() -> None:
        started.set()
        await release.wait()
        _mark_transport_connected(runtime)

    runtime._ws.reconnect = ws_reconnect  # type: ignore[method-assign]
    with patch.object(runtime, "backfill_symbol", side_effect=_noop_backfill):
        first = asyncio.create_task(runtime.reconnect(_eval_time()))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        second = asyncio.create_task(runtime.reconnect(_eval_time()))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=1.0)

    assert runtime._ws.status == ConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_reconnect_sets_connected_after_success() -> None:
    runtime = _runtime()
    _mark_ready(runtime)
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001

    async def ws_reconnect() -> None:
        _mark_transport_connected(runtime)

    runtime._ws.reconnect = ws_reconnect  # type: ignore[method-assign]
    with patch.object(runtime, "backfill_symbol", side_effect=_noop_backfill):
        await runtime.reconnect(_eval_time())

    assert runtime._ws.status == ConnectionStatus.CONNECTED
    assert runtime._last_error == "market_data_readiness_not_recovered"


@pytest.mark.asyncio
async def test_connection_closed_on_ping_sets_reconnecting() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        heartbeat_interval_seconds=0.01,
        pong_timeout_seconds=60.0,
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    for ack in all_ack_messages(config):
        await incoming.put(ack)

    class PingClosingConnection(FakeWebSocketConnection):
        async def send(self, message: str) -> None:
            if '"ping"' in message:
                raise HyperliquidWebSocketError("ConnectionClosedOK: sent 1000 (OK)")
            await super().send(message)

    async def connect(_: str) -> PingClosingConnection:
        return PingClosingConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(_eval_time()),
        sleep=immediate_sleep,
    )
    await feed.connect_and_subscribe()
    await asyncio.sleep(0.05)
    if feed._heartbeat_task is not None:  # noqa: SLF001
        await asyncio.wait_for(feed._heartbeat_task, timeout=1.0)
    assert feed.status == ConnectionStatus.RECONNECTING
    assert feed.background_error is not None
    await feed.disconnect()


@pytest.mark.asyncio
async def test_connection_closed_on_recv_sets_reconnecting() -> None:
    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    for ack in all_ack_messages(config):
        await incoming.put(ack)

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(_eval_time()),
        sleep=immediate_sleep,
    )
    await feed.connect_and_subscribe()
    await incoming.put(None)
    if feed._reader_task is not None:  # noqa: SLF001
        await asyncio.wait_for(feed._reader_task, timeout=1.0)
    assert feed.status == ConnectionStatus.RECONNECTING
    assert feed.background_error is not None
    await feed.disconnect()


def test_wrap_websocket_transport_error_maps_connection_closed() -> None:
    wrapped = wrap_websocket_transport_error(ConnectionClosedOK("sent 1000 (OK)"))
    assert isinstance(wrapped, HyperliquidWebSocketError)
    assert "ConnectionClosedOK" in str(wrapped)


@pytest.mark.asyncio
async def test_reconnect_timeout_does_not_hang() -> None:
    runtime = _runtime(reconnect_total_timeout_seconds=0.05)
    _mark_ready(runtime)
    runtime._ws._status = ConnectionStatus.RECONNECTING  # noqa: SLF001

    async def slow_ws_reconnect() -> None:
        await asyncio.sleep(1.0)

    runtime._ws.reconnect = slow_ws_reconnect  # type: ignore[method-assign]
    with pytest.raises(HyperliquidWebSocketError, match="reconnect exceeded"):
        await asyncio.wait_for(runtime.reconnect(_eval_time()), timeout=1.0)
    assert runtime._last_error is not None


@pytest.mark.asyncio
async def test_shutdown_during_reconnect_cleans_up_tasks() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        reconnect_initial_delay_seconds=0.001,
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(_eval_time()),
        sleep=immediate_sleep,
    )
    feed._status = ConnectionStatus.RECONNECTING  # noqa: SLF001
    reconnect_task = asyncio.create_task(feed.reconnect())
    await asyncio.sleep(0.001)
    await feed.disconnect()
    if not reconnect_task.done():
        reconnect_task.cancel()
        try:
            await reconnect_task
        except (asyncio.CancelledError, HyperliquidWebSocketError):
            pass
    assert reconnect_task.done()
    assert feed.status == ConnectionStatus.SHUTDOWN
