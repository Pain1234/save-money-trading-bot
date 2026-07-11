"""Typed configuration for Hyperliquid public market data."""

from __future__ import annotations

import os
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from market_data.models import MarketSymbol, MarketTimeframe

DEFAULT_MAINNET_HTTP = "https://api.hyperliquid.xyz"
DEFAULT_MAINNET_WS = "wss://api.hyperliquid.xyz/ws"
DEFAULT_TESTNET_HTTP = "https://api.hyperliquid-testnet.xyz"
DEFAULT_TESTNET_WS = "wss://api.hyperliquid-testnet.xyz/ws"


class HyperliquidNetwork(StrEnum):
    MAINNET = "mainnet"
    TESTNET = "testnet"


class HyperliquidPublicConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    network: HyperliquidNetwork = HyperliquidNetwork.TESTNET
    http_base_url: str = DEFAULT_TESTNET_HTTP
    websocket_url: str = DEFAULT_TESTNET_WS
    request_timeout_seconds: float = 10.0
    connect_timeout_seconds: float = 10.0
    heartbeat_interval_seconds: float = 30.0
    pong_timeout_seconds: float = 60.0
    subscription_ack_timeout_seconds: float = 10.0
    reconnect_initial_delay_seconds: float = 1.0
    reconnect_max_delay_seconds: float = 30.0
    max_reconnect_attempts: int | None = None
    max_http_retries: int = 3
    max_pagination_pages: int = 20
    max_candles_per_snapshot: int = 5000
    max_http_concurrency: int = 2
    reconnect_buffer_size: int = 500
    user_agent: str = "save-money-bot-market-data/1.0"
    symbols: tuple[MarketSymbol, ...] = (
        MarketSymbol.BTC,
        MarketSymbol.ETH,
        MarketSymbol.SOL,
    )
    timeframes: tuple[MarketTimeframe, ...] = (
        MarketTimeframe.DAILY,
        MarketTimeframe.WEEKLY,
        MarketTimeframe.MONTHLY,
    )
    meta_cache_ttl_seconds: float = 300.0

    @classmethod
    def for_network(
        cls, network: HyperliquidNetwork, **overrides: object
    ) -> HyperliquidPublicConfig:
        if network == HyperliquidNetwork.MAINNET:
            base = cls(
                network=network,
                http_base_url=DEFAULT_MAINNET_HTTP,
                websocket_url=DEFAULT_MAINNET_WS,
            )
        else:
            base = cls(network=network)
        if overrides:
            return base.model_copy(update=overrides)
        return base

    @classmethod
    def from_env(cls) -> HyperliquidPublicConfig:
        network_raw = os.getenv("HYPERLIQUID_NETWORK", "testnet").lower()
        network = (
            HyperliquidNetwork.MAINNET
            if network_raw == "mainnet"
            else HyperliquidNetwork.TESTNET
        )
        cfg = cls.for_network(network)
        updates: dict[str, object] = {}
        if timeout := os.getenv("HYPERLIQUID_HTTP_TIMEOUT_SECONDS"):
            updates["request_timeout_seconds"] = float(timeout)
        if hb := os.getenv("HYPERLIQUID_HEARTBEAT_INTERVAL_SECONDS"):
            updates["heartbeat_interval_seconds"] = float(hb)
        if initial := os.getenv("HYPERLIQUID_RECONNECT_INITIAL_SECONDS"):
            updates["reconnect_initial_delay_seconds"] = float(initial)
        if maximum := os.getenv("HYPERLIQUID_RECONNECT_MAX_SECONDS"):
            updates["reconnect_max_delay_seconds"] = float(maximum)
        if concurrency := os.getenv("HYPERLIQUID_MAX_HTTP_CONCURRENCY"):
            updates["max_http_concurrency"] = int(concurrency)
        return cfg.model_copy(update=updates) if updates else cfg


def all_subscriptions(
    config: HyperliquidPublicConfig,
) -> tuple[tuple[MarketSymbol, MarketTimeframe], ...]:
    return tuple((sym, tf) for sym in config.symbols for tf in config.timeframes)
