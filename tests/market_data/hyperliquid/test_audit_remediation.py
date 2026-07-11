# ruff: noqa: E402
"""Regression tests for Hyperliquid adapter audit remediations."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import (
    MarketSymbol,
    MarketTimeframe,
    RawCandle,
)
from market_data.network.errors import (
    HyperliquidHttpStatusError,
    HyperliquidPaginationIncompleteError,
)
from market_data.network.http_client import HyperliquidHttpClient
from market_data.network.websocket_client import FakeWebSocketConnection
from market_data.providers.hyperliquid_historical import HyperliquidHistoricalProvider
from market_data.providers.hyperliquid_ws import HyperliquidWebSocketFeed
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService
from market_data.validation import validate_raw_candle
from pydantic import ValidationError

from tests.market_data.hyperliquid.conftest import (
    MockInfoRouter,
    PaginatedMockRouter,
    candle_dict,
    fixed_clock,
    immediate_sleep,
    make_http_client,
    meta_response,
    ws_ack,
    ws_candle,
)


def _make_runtime(
    *,
    config: HyperliquidPublicConfig | None = None,
    ws: HyperliquidWebSocketFeed | None = None,
    http: HyperliquidHttpClient | None = None,
) -> HyperliquidMarketDataRuntime:
    config = config or HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )
    repo = InMemoryCandleRepository()
    service = MarketDataService(repo)
    return HyperliquidMarketDataRuntime(service, config, http_client=http, ws_feed=ws)


@pytest.mark.asyncio
async def test_readiness_false_when_series_incomplete() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )
    eval_time = datetime(2024, 6, 1, tzinfo=UTC)
    runtime = _make_runtime(config=config)
    runtime._meta_ok = True  # noqa: SLF001
    runtime._backfill_ok = True  # noqa: SLF001
    runtime._initial_backfill_done = True  # noqa: SLF001
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    await incoming.put(ws_ack("BTC", "1d"))

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=[])

    ws = HyperliquidWebSocketFeed(
        config, connect_fn=connect, clock=fixed_clock(eval_time), sleep=immediate_sleep
    )
    await ws.connect_and_subscribe()
    runtime._ws = ws
    status = runtime.status(eval_time)
    assert status.readiness is False
    await ws.disconnect()


@pytest.mark.asyncio
async def test_pagination_incomplete_after_max_pages_raises() -> None:
    t0 = 1_700_000_000_000
    t1 = t0 + 86_400_000
    pages = {
        t0: [candle_dict(t=t0, big_t=t0 + 86_399_000)],
        t0 + 86_400_000: [candle_dict(t=t1, big_t=t1 + 86_399_000)],
    }
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET, max_pagination_pages=1, max_candles_per_snapshot=1
    )
    router = PaginatedMockRouter(pages, max_per_page=1)
    client = make_http_client(router, config)
    provider = HyperliquidHistoricalProvider(client, config)
    start_dt = datetime.fromtimestamp(t0 / 1000, tz=UTC)
    end = datetime.fromtimestamp((t1 + 86_400_000 * 5) / 1000, tz=UTC)
    with pytest.raises(HyperliquidPaginationIncompleteError):
        await provider.fetch_candles(
            MarketSymbol.BTC, MarketTimeframe.DAILY, start_dt, end, start_dt
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_pagination_stagnant_timestamp_raises() -> None:
    t = 1_704_067_200_000
    close1 = t + 86_399_000
    close2 = t + 86_400_000
    close3 = t + 86_500_000
    c1 = candle_dict(t=t, big_t=close1)
    c2 = candle_dict(t=t, big_t=close2, c="106")
    c3 = candle_dict(t=t, big_t=close3, c="107")
    router = PaginatedMockRouter({t: [c1], close1 + 1: [c2], close2 + 1: [c3]})
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        max_pagination_pages=5,
        max_candles_per_snapshot=1,
    )
    client = make_http_client(router, config)
    provider = HyperliquidHistoricalProvider(client, config)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 3, 1, tzinfo=UTC)
    with pytest.raises(HyperliquidPaginationIncompleteError, match="stagnant"):
        await provider.fetch_candles(
            MarketSymbol.BTC, MarketTimeframe.DAILY, start, end, start
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_candle_before_ack_buffered_not_live_queued() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        subscription_ack_timeout_seconds=5.0,
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    candle_msg = ws_candle(candle_dict())

    async def connect(_: str) -> FakeWebSocketConnection:
        await incoming.put(candle_msg)
        await incoming.put(ws_ack("BTC", "1d"))
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    feed.begin_buffer()
    await feed.connect_and_subscribe()
    assert feed.subscriptions_acknowledged == 1
    live = await feed.drain_events()
    assert live == ()
    buffered = feed.end_buffer()
    assert len(buffered) == 1
    await feed.disconnect()


@pytest.mark.asyncio
async def test_candle_before_ack_without_buffer_not_ingested() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    candle_msg = ws_candle(candle_dict())

    async def connect(_: str) -> FakeWebSocketConnection:
        await incoming.put(candle_msg)
        await incoming.put(ws_ack("BTC", "1d"))
        return FakeWebSocketConnection(incoming, outgoing=[])

    feed = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    await feed.connect_and_subscribe()
    events = await feed.drain_events()
    assert events == ()
    await feed.disconnect()


@pytest.mark.asyncio
async def test_meta_ok_snapshot_fail_readiness_false() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )

    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body.get("type") == "meta":
            return httpx.Response(200, json=meta_response())
        raise HyperliquidPaginationIncompleteError("partial snapshot")

    client = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
    )
    runtime = _make_runtime(config=config, http=client)
    eval_time = datetime(2024, 1, 2, tzinfo=UTC)
    with pytest.raises(HyperliquidPaginationIncompleteError):
        await runtime.backfill_symbol(
            MarketSymbol.BTC,
            MarketTimeframe.DAILY,
            datetime(2024, 1, 1, tzinfo=UTC),
            eval_time,
            eval_time,
        )
    assert runtime._meta_ok is False  # noqa: SLF001
    assert runtime._backfill_ok is False  # noqa: SLF001
    assert runtime._last_error is not None  # noqa: SLF001
    await client.aclose()


@pytest.mark.asyncio
async def test_http_timeout_retried_then_succeeds() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET, max_http_retries=3, reconnect_initial_delay_seconds=0.001
    )
    attempts = {"n": 0}

    async def handle(_: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json=meta_response())

    client = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
        sleep=immediate_sleep,
    )
    result = await client.post_info({"type": "meta"})
    assert result == meta_response()
    assert attempts["n"] == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_http_400_not_retried() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET, max_http_retries=3, reconnect_initial_delay_seconds=0.001
    )
    attempts = {"n": 0}

    async def handle(_: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(400, text="bad")

    client = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
        sleep=immediate_sleep,
    )
    with pytest.raises(HyperliquidHttpStatusError):
        await client.post_info({"type": "meta"})
    assert attempts["n"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_cold_start_buffers_event_during_ack() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )
    router = MockInfoRouter()
    router.set_meta()
    router.set_snapshot([candle_dict()])
    http = make_http_client(router, config)

    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    candle_msg = ws_candle(candle_dict(c="102"))

    async def connect(_: str) -> FakeWebSocketConnection:
        await incoming.put(candle_msg)
        await incoming.put(ws_ack("BTC", "1d"))
        return FakeWebSocketConnection(incoming, outgoing=[])

    ws = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 1, 2, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    runtime = _make_runtime(config=config, http=http, ws=ws)
    eval_time = datetime(2024, 1, 2, tzinfo=UTC)
    await runtime.start(eval_time)
    assert runtime.repository.get_range(MarketSymbol.BTC, MarketTimeframe.DAILY)
    await runtime.aclose()


def test_decimal_exact_preservation() -> None:
    raw = RawCandle(
        provider_symbol="BTC",
        timeframe=MarketTimeframe.DAILY,
        open_time=datetime(2024, 1, 1, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        open=Decimal("42000.123456789"),
        high=Decimal("42000.123456789"),
        low=Decimal("42000.123456789"),
        close=Decimal("42000.123456789"),
        volume=Decimal("0.000000001"),
        is_closed=True,
    )
    assert validate_raw_candle(raw) == ()


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValidationError):
        HyperliquidPublicConfig.for_network(
            HyperliquidNetwork.TESTNET,
            reconnect_initial_delay_seconds=10,
            reconnect_max_delay_seconds=1,
        )


@pytest.mark.asyncio
async def test_disconnect_clears_readiness() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
    )
    incoming: asyncio.Queue[str | None] = asyncio.Queue()
    await incoming.put(ws_ack("BTC", "1d"))

    async def connect(_: str) -> FakeWebSocketConnection:
        return FakeWebSocketConnection(incoming, outgoing=[])

    ws = HyperliquidWebSocketFeed(
        config,
        connect_fn=connect,
        clock=fixed_clock(datetime(2024, 6, 1, tzinfo=UTC)),
        sleep=immediate_sleep,
    )
    runtime = _make_runtime(config=config, ws=ws)
    runtime._meta_ok = True  # noqa: SLF001
    runtime._backfill_ok = True  # noqa: SLF001
    runtime._initial_backfill_done = True  # noqa: SLF001
    await ws.connect_and_subscribe()
    await ws.disconnect()
    status = runtime.status(datetime(2024, 6, 1, tzinfo=UTC))
    assert status.readiness is False
