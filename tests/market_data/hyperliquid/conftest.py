# ruff: noqa: E402
"""Shared Hyperliquid test fixtures."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from datetime import datetime

import httpx
import pytest
from market_data.config import (
    DEFAULT_TESTNET_HTTP,
    DEFAULT_TESTNET_WS,
    HyperliquidNetwork,
    HyperliquidPublicConfig,
)
from market_data.network.http_client import HyperliquidHttpClient
from market_data.providers.hyperliquid import coin_for_symbol, interval_for_timeframe

LIVE_ENV_FLAG = "RUN_HYPERLIQUID_LIVE_TESTS"
NETWORK_ENV_FLAG = "HYPERLIQUID_NETWORK"

_FORBIDDEN_SECRET_ENV = (
    "HYPERLIQUID_PRIVATE_KEY",
    "PRIVATE_KEY",
    "WALLET_ADDRESS",
    "HYPERLIQUID_API_SECRET",
)


def require_testnet_live() -> None:
    """Skip unless live testnet smoke tests are explicitly enabled."""
    if os.getenv(LIVE_ENV_FLAG) != "1":
        pytest.skip(f"{LIVE_ENV_FLAG} not enabled")
    network = os.getenv(NETWORK_ENV_FLAG, "").strip().lower()
    if network != "testnet":
        pytest.skip(
            f"{NETWORK_ENV_FLAG} must be 'testnet' for live smoke tests (got {network!r})"
        )


def assert_public_read_only_safety(config: HyperliquidPublicConfig) -> None:
    """Fail closed if secrets are present or endpoints are not public testnet."""
    for key in _FORBIDDEN_SECRET_ENV:
        if os.getenv(key):
            pytest.fail(f"Refusing live smoke test with secret env var: {key}")
    assert config.network == HyperliquidNetwork.TESTNET
    assert config.http_base_url == DEFAULT_TESTNET_HTTP
    assert config.websocket_url == DEFAULT_TESTNET_WS
    assert "testnet" in config.http_base_url.lower()
    assert "/exchange" not in config.http_base_url


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

    def set_meta(self, payload: dict[str, object] | None = None) -> None:
        self.handlers["meta"] = payload or meta_response()

    def set_snapshot(self, candles: list[dict[str, object]]) -> None:
        self.handlers["candleSnapshot"] = candles

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        self.requests.append(body)
        req_type = body.get("type")
        if req_type == "meta":
            payload = self.handlers.get("meta", meta_response())
            return httpx.Response(200, json=payload)
        if req_type == "candleSnapshot":
            payload = self.handlers.get("candleSnapshot", [])
            return httpx.Response(200, json=payload)
        return httpx.Response(400, text="unknown")


def make_http_client(
    router: MockInfoRouter, config: HyperliquidPublicConfig | None = None
) -> HyperliquidHttpClient:
    from market_data.config import HyperliquidNetwork

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
