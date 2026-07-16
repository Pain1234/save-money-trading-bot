"""Venue, network, and instrument classification enums."""

from __future__ import annotations

from enum import StrEnum


class Venue(StrEnum):
    """Execution / market-data venue (not a provider-internal id)."""

    HYPERLIQUID = "hyperliquid"


class Network(StrEnum):
    """Venue network plane."""

    MAINNET = "mainnet"
    TESTNET = "testnet"


class InstrumentType(StrEnum):
    """Contract / product type."""

    PERPETUAL = "perpetual"


class AssetClass(StrEnum):
    """High-level asset class."""

    CRYPTO = "crypto"
