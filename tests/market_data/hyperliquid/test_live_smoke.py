# ruff: noqa: E402
"""Real Hyperliquid testnet smoke tests — public endpoints only, no wallet."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from market_data.config import HyperliquidPublicConfig
from market_data.models import ConnectionStatus, MarketSymbol, MarketTimeframe
from market_data.network.http_client import HyperliquidHttpClient
from market_data.network.websocket_client import (
    default_websocket_connect,
    dumps_message,
    parse_ws_message,
)
from market_data.providers.hyperliquid import coin_for_symbol
from market_data.providers.hyperliquid_historical import HyperliquidHistoricalProvider
from market_data.providers.hyperliquid_meta import fetch_perpetual_meta
from market_data.providers.hyperliquid_ws import HyperliquidWebSocketFeed
from market_data.timeframes import ensure_utc, is_candle_closed

from tests.market_data.hyperliquid.conftest import (
    LIVE_ENV_FLAG,
    NETWORK_ENV_FLAG,
    assert_public_read_only_safety,
    require_testnet_live,
)

_LIVE_TEST_TIMEOUT_SECONDS = 15.0


def test_live_guard_skips_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LIVE_ENV_FLAG, raising=False)
    monkeypatch.delenv(NETWORK_ENV_FLAG, raising=False)
    with pytest.raises(pytest.skip.Exception, match=LIVE_ENV_FLAG):
        require_testnet_live()


def test_live_guard_skips_when_network_not_testnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LIVE_ENV_FLAG, "1")
    monkeypatch.setenv(NETWORK_ENV_FLAG, "mainnet")
    with pytest.raises(pytest.skip.Exception, match="testnet"):
        require_testnet_live()


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_testnet_fetches_perpetual_meta(
    live_testnet_config: HyperliquidPublicConfig,
    live_http_client: HyperliquidHttpClient,
) -> None:
    """POST /info type=meta against public testnet — no wallet, no exchange endpoint."""
    assert_public_read_only_safety(live_testnet_config)
    try:
        universe = await asyncio.wait_for(
            fetch_perpetual_meta(live_http_client, live_testnet_config),
            timeout=_LIVE_TEST_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        pytest.fail(f"Meta fetch timed out after {_LIVE_TEST_TIMEOUT_SECONDS}s")
    except Exception as exc:
        pytest.fail(
            f"Meta fetch failed against {live_testnet_config.http_base_url}/info: {exc}"
        )

    assert isinstance(universe, frozenset)
    assert len(universe) > 0
    assert "BTC" in universe
    assert {"BTC", "ETH", "SOL"}.issubset(universe)


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_testnet_fetches_small_daily_candle_snapshot(
    live_testnet_config: HyperliquidPublicConfig,
    live_http_client: HyperliquidHttpClient,
) -> None:
    """Small BTC 1d candleSnapshot via historical provider — closed candles only."""
    assert_public_read_only_safety(live_testnet_config)
    snapshot_config = live_testnet_config.model_copy(
        update={"max_pagination_pages": 1, "max_http_retries": 1}
    )
    provider = HyperliquidHistoricalProvider(live_http_client, snapshot_config)
    evaluation_time = datetime.now(tz=UTC)
    start_time = evaluation_time - timedelta(days=7)
    end_time = evaluation_time

    try:
        candles = await asyncio.wait_for(
            provider.fetch_candles(
                MarketSymbol.BTC,
                MarketTimeframe.DAILY,
                start_time,
                end_time,
                evaluation_time,
            ),
            timeout=_LIVE_TEST_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        pytest.fail(f"Candle snapshot timed out after {_LIVE_TEST_TIMEOUT_SECONDS}s")
    except Exception as exc:
        pytest.fail(
            f"Candle snapshot failed against {snapshot_config.http_base_url}/info: {exc}"
        )

    closed_candles = tuple(c for c in candles if is_candle_closed(c.close_time, evaluation_time))
    assert len(closed_candles) >= 1, "Expected at least one closed daily BTC candle"

    expected_coin = coin_for_symbol(MarketSymbol.BTC)
    for candle in closed_candles:
        assert candle.provider_symbol.upper() == expected_coin
        assert candle.timeframe == MarketTimeframe.DAILY
        assert candle.open > Decimal(0)
        assert candle.high > Decimal(0)
        assert candle.low > Decimal(0)
        assert candle.close > Decimal(0)
        assert candle.volume >= Decimal(0)
        assert ensure_utc(candle.close_time) > ensure_utc(candle.open_time)
        assert candle.open_time.tzinfo is not None
        assert candle.close_time.tzinfo is not None

    for prev, curr in zip(closed_candles, closed_candles[1:], strict=False):
        assert prev.open_time <= curr.open_time, "Candles must be chronological"


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_testnet_websocket_subscription_ack(
    live_testnet_config: HyperliquidPublicConfig,
) -> None:
    """Single BTC/1d WebSocket subscription ack on public testnet."""
    assert_public_read_only_safety(live_testnet_config)
    ws_config = live_testnet_config.model_copy(
        update={
            "symbols": (MarketSymbol.BTC,),
            "timeframes": (MarketTimeframe.DAILY,),
            "subscription_ack_timeout_seconds": 12.0,
            "heartbeat_interval_seconds": 120.0,
        }
    )
    feed = HyperliquidWebSocketFeed(ws_config)
    try:
        await asyncio.wait_for(feed.connect_and_subscribe(), timeout=_LIVE_TEST_TIMEOUT_SECONDS)
        assert feed.subscriptions_expected == 1
        assert feed.subscriptions_acknowledged == 1
        assert feed.status == ConnectionStatus.CONNECTED
    except TimeoutError:
        pytest.fail(
            f"WebSocket subscription ack timed out after {_LIVE_TEST_TIMEOUT_SECONDS}s"
        )
    except Exception as exc:
        pytest.fail(
            f"WebSocket connect failed against {ws_config.websocket_url}: {exc}"
        )
    finally:
        await feed.disconnect()
        assert feed.status == ConnectionStatus.SHUTDOWN


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_testnet_ping_pong(live_testnet_config: HyperliquidPublicConfig) -> None:
    """Direct ping/pong on public testnet WebSocket — isolated from feed heartbeat."""
    assert_public_read_only_safety(live_testnet_config)
    conn = None
    try:
        conn = await asyncio.wait_for(
            default_websocket_connect(live_testnet_config.websocket_url),
            timeout=_LIVE_TEST_TIMEOUT_SECONDS,
        )
        await asyncio.wait_for(
            conn.send(dumps_message({"method": "ping"})),
            timeout=5.0,
        )
        raw = await asyncio.wait_for(conn.recv(), timeout=5.0)
        payload = parse_ws_message(raw)
        assert isinstance(payload, dict), f"Expected pong object, got {payload!r}"
        assert payload.get("channel") == "pong", f"Expected pong channel, got {payload!r}"
    except TimeoutError:
        pytest.fail(f"Ping/pong timed out against {live_testnet_config.websocket_url}")
    except Exception as exc:
        pytest.fail(f"Ping/pong failed: {exc}")
    finally:
        if conn is not None:
            await conn.close()
