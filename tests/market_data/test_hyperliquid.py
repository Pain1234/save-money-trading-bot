# ruff: noqa: E402
"""Hyperliquid adapter parsing tests."""

from __future__ import annotations

from market_data.models import MarketTimeframe
from market_data.providers.hyperliquid import HyperliquidCandleAdapter


def test_parse_hyperliquid_candle_payload() -> None:
    adapter = HyperliquidCandleAdapter()
    payload = {
        "s": "BTC",
        "i": "1d",
        "t": 1704067200000,
        "T": 1704153599000,
        "o": "42000",
        "h": "43000",
        "l": "41000",
        "c": "42500",
        "v": "1234.5",
        "closed": True,
    }
    raw = adapter.parse_candle(payload)
    assert raw.provider_symbol == "BTC"
    assert raw.timeframe == MarketTimeframe.DAILY
    assert raw.open > 0
    assert raw.is_closed is True
