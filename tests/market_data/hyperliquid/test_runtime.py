# ruff: noqa: E402
"""Hyperliquid runtime integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.network.http_client import HyperliquidHttpClient
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService

from tests.market_data.hyperliquid.conftest import candle_dict, meta_response


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
@pytest.mark.live
async def test_live_smoke_skipped_by_default() -> None:
    import os

    if os.getenv("RUN_HYPERLIQUID_LIVE_TESTS") != "1":
        pytest.skip("RUN_HYPERLIQUID_LIVE_TESTS not enabled")
