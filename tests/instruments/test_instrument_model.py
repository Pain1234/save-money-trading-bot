"""Unit tests for canonical instrument model (P4.1 / #128)."""

from __future__ import annotations

import pytest
from market_data.models import MarketSymbol

from instruments import (
    INSTRUMENT_REGISTRY,
    AssetClass,
    Instrument,
    InstrumentId,
    InstrumentType,
    Network,
    Venue,
    get_instrument,
    get_instrument_by_id,
    instrument_id_to_legacy_symbol,
    instrument_to_market_symbol,
    list_supported_instruments,
    resolve_instrument,
    resolve_legacy_symbol,
    to_market_symbol,
)
from instruments.identity import make_instrument_id, parse_instrument_id
from instruments.legacy import normalize_legacy_symbol


def test_registry_contains_exactly_btc_eth_sol() -> None:
    instruments = list_supported_instruments()
    assert len(instruments) == 3
    assert [i.legacy_symbol for i in instruments] == ["BTC", "ETH", "SOL"]
    assert len(INSTRUMENT_REGISTRY) == 3
    assert all(i.active for i in instruments)


def test_instrument_id_roundtrip() -> None:
    for legacy in ("BTC", "ETH", "SOL"):
        inst = get_instrument(legacy)
        parsed = parse_instrument_id(inst.instrument_id)
        rebuilt = make_instrument_id(
            venue=parsed[0],
            network=parsed[1],
            instrument_type=parsed[2],
            base_symbol=parsed[3],
        )
        assert rebuilt == inst.instrument_id
        assert get_instrument_by_id(rebuilt) is inst
        assert instrument_id_to_legacy_symbol(inst.instrument_id) == legacy


def test_legacy_symbol_resolve() -> None:
    assert resolve_legacy_symbol("BTC").legacy_symbol == "BTC"
    assert resolve_legacy_symbol("eth-usd").legacy_symbol == "ETH"
    assert resolve_legacy_symbol("SOLUSDT").legacy_symbol == "SOL"
    assert resolve_legacy_symbol(MarketSymbol.ETH).base_symbol == "ETH"
    assert to_market_symbol("BTC-USD") is MarketSymbol.BTC
    assert instrument_to_market_symbol(get_instrument("SOL")) is MarketSymbol.SOL


def test_unknown_symbol_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        get_instrument("DOGE")
    with pytest.raises(ValueError, match="Unknown"):
        normalize_legacy_symbol("HYPE")
    with pytest.raises(ValueError, match="Unknown"):
        resolve_instrument("DOGE")
    with pytest.raises(ValueError, match="Unknown InstrumentId"):
        get_instrument_by_id("hyperliquid:mainnet:perpetual:DOGE")
    with pytest.raises(ValueError, match="Invalid InstrumentId"):
        parse_instrument_id("not-an-id")


def test_hl_perp_identity_fields() -> None:
    for legacy in ("BTC", "ETH", "SOL"):
        inst = get_instrument(legacy)
        assert inst.venue is Venue.HYPERLIQUID
        assert inst.network is Network.MAINNET
        assert inst.instrument_type is InstrumentType.PERPETUAL
        assert inst.asset_class is AssetClass.CRYPTO
        assert inst.quote_symbol == "USD"
        assert inst.instrument_id == InstrumentId(f"hyperliquid:mainnet:perpetual:{legacy}")
        assert isinstance(inst, Instrument)


def test_resolve_instrument_accepts_id_and_alias() -> None:
    btc = get_instrument("BTC")
    assert resolve_instrument(btc.instrument_id) is btc
    assert resolve_instrument("BTCUSDT") is btc
