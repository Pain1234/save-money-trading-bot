"""Legacy MarketSymbol / string-symbol compatibility bridges."""

from __future__ import annotations

from market_data.models import MarketSymbol

from instruments.identity import Instrument, InstrumentId
from instruments.registry import get_instrument, get_instrument_by_id

# Aliases accepted by market_data.symbols.resolve_internal_symbol (and bare symbols).
_LEGACY_ALIASES: dict[str, str] = {
    "BTC": "BTC",
    "ETH": "ETH",
    "SOL": "SOL",
    "BTC-USD": "BTC",
    "ETH-USD": "ETH",
    "SOL-USD": "SOL",
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
}


def normalize_legacy_symbol(symbol: str) -> str:
    """Map legacy / provider alias to canonical BTC|ETH|SOL; fail-closed."""
    normalized = symbol.strip().upper()
    if normalized in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[normalized]
    raise ValueError(f"Unknown legacy symbol: {symbol!r}")


def resolve_legacy_symbol(symbol: str | MarketSymbol) -> Instrument:
    """Resolve a legacy symbol string or MarketSymbol to Instrument."""
    if isinstance(symbol, MarketSymbol):
        return get_instrument(symbol.value)
    return get_instrument(normalize_legacy_symbol(str(symbol)))


def to_market_symbol(instrument: Instrument | InstrumentId | str) -> MarketSymbol:
    """Bridge Instrument / InstrumentId / legacy symbol → MarketSymbol."""
    if isinstance(instrument, Instrument):
        return MarketSymbol(instrument.legacy_symbol)
    raw = str(instrument).strip()
    if raw.count(":") == 3:
        return MarketSymbol(get_instrument_by_id(raw).legacy_symbol)
    return MarketSymbol(normalize_legacy_symbol(raw))


def instrument_to_market_symbol(instrument: Instrument) -> MarketSymbol:
    """Map canonical Instrument to legacy MarketSymbol."""
    return MarketSymbol(instrument.legacy_symbol)


def instrument_id_to_legacy_symbol(instrument_id: InstrumentId | str) -> str:
    """Map InstrumentId → legacy symbol string (BTC/ETH/SOL)."""
    return get_instrument_by_id(instrument_id).legacy_symbol
