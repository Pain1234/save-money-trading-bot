# ruff: noqa: E402
"""Shared helpers for Hyperliquid live smoke tests (non-pytest module for mypy)."""

from __future__ import annotations

import os

import pytest
from market_data.config import (
    DEFAULT_TESTNET_HTTP,
    DEFAULT_TESTNET_WS,
    HyperliquidNetwork,
    HyperliquidPublicConfig,
)

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
