"""Canonical instrument identity for P4 universe research.

Additive layer: does not change MarketSymbol or P2.5 trading behavior.
"""

from instruments.enums import AssetClass, InstrumentType, Network, Venue
from instruments.identity import Instrument, InstrumentId
from instruments.legacy import (
    instrument_id_to_legacy_symbol,
    instrument_to_market_symbol,
    resolve_legacy_symbol,
    to_market_symbol,
)
from instruments.registry import (
    INSTRUMENT_REGISTRY,
    SUPPORTED_LEGACY_SYMBOLS,
    get_instrument,
    get_instrument_by_id,
    list_supported_instruments,
    resolve_instrument,
)

__all__ = [
    "AssetClass",
    "INSTRUMENT_REGISTRY",
    "Instrument",
    "InstrumentId",
    "InstrumentType",
    "Network",
    "SUPPORTED_LEGACY_SYMBOLS",
    "Venue",
    "get_instrument",
    "get_instrument_by_id",
    "instrument_id_to_legacy_symbol",
    "instrument_to_market_symbol",
    "list_supported_instruments",
    "resolve_instrument",
    "resolve_legacy_symbol",
    "to_market_symbol",
]
