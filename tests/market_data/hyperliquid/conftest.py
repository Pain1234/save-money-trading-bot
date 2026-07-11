# ruff: noqa: E402
"""Shared Hyperliquid test fixtures."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime

import httpx
import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.network.http_client import HyperliquidHttpClient
from market_data.providers.hyperliquid import coin_for_symbol, interval_for_timeframe

from tests.market_data.hyperliquid.live_support import (
    assert_public_read_only_safety,
    require_testnet_live,
)

__all__ = [
    "assert_public_read_only_safety",
    "require_testnet_live",
    "candle_dict",
    "meta_response",
    "ws_ack",
    "ws_candle",
    "MockInfoRouter",
    "PaginatedMockRouter",
    "make_http_client",
    "all_ack_messages",
    "immediate_sleep",
    "fixed_clock",
    "live_testnet_config",
    "live_http_client",
]


def candle_dict(
    *,
    coin: str = "BTC",
    interval: str = "1d",
    t: int = 1704067200000,
    big_t: int = 1704153599000,
    o: str = "100",
    h: str = "110",
    low: str = "90",
    c: str = "105",
    v: str = "1000",
    n: int = 42,
) -> dict[str, object]:
    return {
        "s": coin,
        "i": interval,
        "t": t,
        "T": big_t,
        "o": o,
        "h": h,
        "l": low,
        "c": c,
        "v": v,
        "n": n,
    }


def meta_response() -> dict[str, object]:
    return {"universe": [{"name": "BTC"}, {"name": "ETH"}, {"name": "SOL"}]}


def ws_ack(coin: str, interval: str) -> str:
    return json.dumps(
        {
            "channel": "subscriptionResponse",
            "data": {"subscription": {"type": "candle", "coin": coin, "interval": interval}},
        }
    )


def ws_candle(payload: dict[str, object]) -> str:
    return json.dumps({"channel": "candle", "data": payload})


class MockInfoRouter:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.handlers: dict[str, object] = {}
        self.fail_after_meta: Exception | None = None
        self.call_count = 0

    def set_meta(self, payload: dict[str, object] | None = None) -> None:
        self.handlers["meta"] = payload or meta_response()

    def set_snapshot(self, candles: list[dict[str, object]]) -> None:
        self.handlers["candleSnapshot"] = candles

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        self.requests.append(body)
        req_type = body.get("type")
        if req_type == "meta":
            return httpx.Response(200, json=self.handlers.get("meta", meta_response()))
        if req_type == "candleSnapshot":
            self.call_count += 1
            if self.fail_after_meta is not None and self.call_count > 1:
                raise self.fail_after_meta
            payload = self.handlers.get("candleSnapshot", [])
            return httpx.Response(200, json=payload)
        return httpx.Response(400, text="unknown")


class PaginatedMockRouter:
    """Route candleSnapshot by startTime cursor."""

    def __init__(
        self,
        pages_by_start: dict[int, list[dict[str, object]]],
        *,
        max_per_page: int = 5000,
    ) -> None:
        self.pages_by_start = pages_by_start
        self.max_per_page = max_per_page
        self.requests: list[dict[str, object]] = []

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        self.requests.append(body)
        req_type = body.get("type")
        if req_type == "meta":
            return httpx.Response(200, json=meta_response())
        if req_type == "candleSnapshot":
            start = int(body["req"]["startTime"])
            candles = self.pages_by_start.get(start, [])
            return httpx.Response(200, json=candles[: self.max_per_page])
        return httpx.Response(400, text="unknown")


def make_http_client(
    router: MockInfoRouter | PaginatedMockRouter,
    config: HyperliquidPublicConfig | None = None,
) -> HyperliquidHttpClient:
    config = config or HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    transport = httpx.MockTransport(router.handle)
    client = httpx.AsyncClient(transport=transport, base_url=config.http_base_url)
    return HyperliquidHttpClient(config, client=client)


def all_ack_messages(config: HyperliquidPublicConfig) -> list[str]:
    msgs: list[str] = []
    for sym in config.symbols:
        for tf in config.timeframes:
            msgs.append(ws_ack(coin_for_symbol(sym), interval_for_timeframe(tf)))
    return msgs


async def immediate_sleep(_: float) -> None:
    return None


def fixed_clock(at: datetime) -> Callable[[], datetime]:
    return lambda: at


@pytest.fixture
def live_testnet_config() -> HyperliquidPublicConfig:
    require_testnet_live()
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET,
        max_http_retries=1,
        request_timeout_seconds=10.0,
        connect_timeout_seconds=10.0,
    )
    assert_public_read_only_safety(config)
    return config


@pytest.fixture
async def live_http_client(
    live_testnet_config: HyperliquidPublicConfig,
) -> AsyncIterator[HyperliquidHttpClient]:
    client = HyperliquidHttpClient(live_testnet_config)
    try:
        yield client
    finally:
        await client.aclose()
