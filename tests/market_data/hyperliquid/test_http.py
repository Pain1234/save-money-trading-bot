# ruff: noqa: E402
"""Hyperliquid HTTP adapter tests — no real network."""

from __future__ import annotations

import json
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


@pytest.mark.asyncio
async def test_post_info_with_raw_preserves_exact_bytes() -> None:
    config = HyperliquidPublicConfig.for_network(HyperliquidNetwork.TESTNET)
    raw = b'[{"s":"BTC","i":"1d","t":1704067200000,"T":1704153599000,'
    raw += b'"o":"100","h":"110","l":"90","c":"105","v":"1000","n":42}]'

    async def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=raw,
            headers={"content-type": "application/json"},
        )

    client = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
    )
    parsed, captured = await client.post_info_with_raw(
        {"type": "candleSnapshot", "req": {}}, request_id="raw-bytes"
    )
    assert captured == raw
    assert isinstance(parsed, list)
    assert str(parsed[0]["o"]) == "100"
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_candles_with_raw_pages_order_and_roundtrip() -> None:
    """Paginated raw pages keep order; re-parse equals provider candles."""
    from market_data.content_hash import derive_dataset_id, hash_raw_bytes
    from research.hl_dataset_export import raw_candles_from_hl_pages, raw_source_for_network

    day1 = candle_dict(t=1704067200000, big_t=1704153599000, o="100", c="101")
    day2 = candle_dict(t=1704153600000, big_t=1704239999000, o="101", c="102")
    page0 = json_bytes([day1])
    page1 = json_bytes([day2])

    config = HyperliquidPublicConfig.for_network(
        HyperliquidNetwork.TESTNET, max_candles_per_snapshot=1
    )
    call_raw: list[bytes] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        start = int(body["req"]["startTime"])
        # Emit fixed bytes (not httpx json= re-serialize) so capture is exact.
        # Cursor after page0 advances to close_time+1 (= 1704153599001).
        if start == 1704067200000:
            raw = page0
        elif start == 1704153599001:
            raw = page1
        else:
            raw = b"[]"
        call_raw.append(raw)
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    client = HyperliquidHttpClient(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url=config.http_base_url
        ),
    )
    provider = HyperliquidHistoricalProvider(client, config)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 2, 23, 59, 59, tzinfo=UTC)
    candles, pages = await provider.fetch_candles_with_raw_pages(
        MarketSymbol.BTC, MarketTimeframe.DAILY, start, end, end
    )
    assert pages == (page0, page1)
    assert call_raw == [page0, page1]
    assert len(candles) == 2
    replayed = raw_candles_from_hl_pages(pages, symbol=MarketSymbol.BTC, evaluation_time=end)
    assert len(replayed) == 2
    assert replayed[0].open_time == candles[0].open_time
    assert replayed[0].close == candles[0].close
    assert replayed[1].close == candles[1].close

    # Testnet raw identity seed (not mainnet).
    raw_hash = hash_raw_bytes(b"".join(pages))
    testnet_id = derive_dataset_id(
        raw_hash, "1.0", raw_source_for_network(HyperliquidNetwork.TESTNET)
    )
    mainnet_id = derive_dataset_id(
        raw_hash, "1.0", raw_source_for_network(HyperliquidNetwork.MAINNET)
    )
    assert testnet_id != mainnet_id
    await client.aclose()


def json_bytes(items: list[dict[str, object]]) -> bytes:
    return json.dumps(items, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
