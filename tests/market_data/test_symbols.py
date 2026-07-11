# ruff: noqa: E402
"""Symbol mapping tests."""

from __future__ import annotations

import pytest
from market_data.models import MarketSymbol
from market_data.symbols import resolve_internal_symbol, to_provider_symbol


def test_known_symbols() -> None:
    assert resolve_internal_symbol("BTC") == MarketSymbol.BTC
    assert resolve_internal_symbol("ETH-USD") == MarketSymbol.ETH
    assert resolve_internal_symbol("SOLUSDT") == MarketSymbol.SOL


def test_unknown_symbol_fail_closed() -> None:
    with pytest.raises(ValueError, match="Unknown provider symbol"):
        resolve_internal_symbol("DOGE")


def test_hyperliquid_provider_mapping() -> None:
    assert to_provider_symbol(MarketSymbol.BTC, provider="hyperliquid") == "BTC"
