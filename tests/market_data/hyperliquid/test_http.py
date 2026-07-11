# ruff: noqa: E402
"""Hyperliquid HTTP adapter tests — no real network."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.network.errors import (
    HyperliquidHttpStatusError,
    HyperliquidParseError,
)
from market_data.network.http_client import HyperliquidHttpClient
from market_data.network.json_utils import loads_decimal
from market_data.providers.hyperliquid import HyperliquidCandleAdapter
from market_data.providers.hyperliquid_historical import HyperliquidHistoricalProvider
from market_data.providers.hyperliquid_meta import fetch_perpetual_meta

from tests.market_data.hyperliquid.conftest import (
    MockInfoRouter,
    candle_dict,
    immediate_sleep,
    make_http_client,
)


@pytest.mark.asyncio
async def test_meta_contains_btc_eth_sol() -> None:
    router = MockInfoRouter()
    router.set_meta()
    client = make_http_client(router)
    universe = await fetch_perpetual_meta(client, client._config)
    assert {"BTC", "ETH", "SOL"}.issubset(universe)
    await client.aclose()


@pytest.mark.asyncio
async def test_meta_missing_symbol_fail_closed() -> None:
    router = MockInfoRouter()
    router.set_meta({"universe": [{"name": "BTC"}]})
    client = make_http_client(router)
    with pytest.raises(HyperliquidParseError):
        await fetch_perpetual_meta(client, client._config)
    await client.aclose()


@pytest.mark.asyncio
async def test_valid_candle_snapshot() -> None:
    router = MockInfoRouter()
    router.set_snapshot([candle_dict()])
    client = make_http_client(router)
    provider = HyperliquidHistoricalProvider(client, client._config)
    end = datetime(2024, 1, 2, tzinfo=UTC)
    candles = await provider.fetch_candles(
        MarketSymbol.BTC, MarketTimeframe.DAILY, datetime(2024, 1, 1, tzinfo=UTC), end, end
    )
    assert len(candles) == 1
    assert candles[0].open == Decimal("100")
    await client.aclose()


@pytest.mark.asyncio
async def test_empty_snapshot_response() -> None:
    router = MockInfoRouter()
    router.set_snapshot([])
    client = make_http_client(router)
    provider = HyperliquidHistoricalProvider(client, client._config)
    end = datetime(2024, 1, 2, tzinfo=UTC)
    candles = await provider.fetch_candles(
        MarketSymbol.BTC, MarketTimeframe.DAILY, datetime(2024, 1, 1, tzinfo=UTC), end, end
    )
    assert candles == ()
    await client.aclose()


@pytest.mark.asyncio
async def test_wrong_symbol_rejected() -> None:
    adapter = HyperliquidCandleAdapter()
    with pytest.raises(ValueError, match="Symbol mismatch"):
        adapter.parse_candle(
            candle_dict(coin="ETH"),
            expected_coin="BTC",
            expected_interval="1d",
            strict=True,
        )


@pytest.mark.asyncio
async def test_missing_required_field() -> None:
    adapter = HyperliquidCandleAdapter()
    payload = candle_dict()
    del payload["n"]
    with pytest.raises(ValueError, match="Missing required"):
        adapter.parse_candle(payload, strict=True)


@pytest.mark.asyncio
async def test_invalid_json() -> None:
    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)

    async def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
    )
    with pytest.raises(HyperliquidParseError):
        await client.post_info({"type": "meta"})
    await client.aclose()


@pytest.mark.asyncio
async def test_400_no_retry() -> None:
    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET, max_http_retries=3, reconnect_initial_delay_seconds=0.001
    )
    calls = {"n": 0}

    async def handle(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
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
    assert calls["n"] == 1
    await client.aclose()


def test_decimal_without_float_loss() -> None:
    parsed = loads_decimal('{"price":42000.123456789}')
    assert isinstance(parsed["price"], Decimal)
    assert str(parsed["price"]) == "42000.123456789"
