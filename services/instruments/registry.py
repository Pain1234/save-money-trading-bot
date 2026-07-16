"""BTC/ETH/SOL production instrument registry (Hyperliquid perpetuals)."""

from __future__ import annotations

from instruments.enums import AssetClass, InstrumentType, Network, Venue
from instruments.identity import Instrument, InstrumentId, make_instrument_id

# Production P2.5 universe — Hyperliquid mainnet perpetuals only.
_PRODUCTION_BASES: tuple[str, ...] = ("BTC", "ETH", "SOL")


def _hl_perp(base: str) -> Instrument:
    legacy = base.upper()
    return Instrument(
        instrument_id=make_instrument_id(
            venue=Venue.HYPERLIQUID,
            network=Network.MAINNET,
            instrument_type=InstrumentType.PERPETUAL,
            base_symbol=legacy,
        ),
        venue=Venue.HYPERLIQUID,
        network=Network.MAINNET,
        instrument_type=InstrumentType.PERPETUAL,
        asset_class=AssetClass.CRYPTO,
        base_symbol=legacy,
        quote_symbol="USD",
        legacy_symbol=legacy,
        display_name=f"{legacy}-PERP",
        active=True,
    )


INSTRUMENT_REGISTRY: dict[InstrumentId, Instrument] = {
    inst.instrument_id: inst for inst in (_hl_perp(base) for base in _PRODUCTION_BASES)
}

_BY_LEGACY_SYMBOL: dict[str, Instrument] = {
    inst.legacy_symbol: inst for inst in INSTRUMENT_REGISTRY.values()
}

SUPPORTED_LEGACY_SYMBOLS: frozenset[str] = frozenset(_BY_LEGACY_SYMBOL)


def list_supported_instruments() -> tuple[Instrument, ...]:
    """Return active registered instruments in stable BTC, ETH, SOL order."""
    return tuple(_BY_LEGACY_SYMBOL[s] for s in _PRODUCTION_BASES)


def get_instrument_by_id(instrument_id: InstrumentId | str) -> Instrument:
    """Lookup by InstrumentId; fail-closed on unknown."""
    key = InstrumentId(str(instrument_id).strip())
    try:
        return INSTRUMENT_REGISTRY[key]
    except KeyError as exc:
        raise ValueError(f"Unknown InstrumentId: {instrument_id!r}") from exc


def get_instrument(legacy_symbol: str) -> Instrument:
    """Lookup by canonical legacy symbol (BTC/ETH/SOL); fail-closed on unknown."""
    key = legacy_symbol.strip().upper()
    try:
        return _BY_LEGACY_SYMBOL[key]
    except KeyError as exc:
        raise ValueError(f"Unknown legacy symbol: {legacy_symbol!r}") from exc


def resolve_instrument(key: str | InstrumentId) -> Instrument:
    """Resolve InstrumentId or legacy/alias symbol; fail-closed on unknown."""
    raw = str(key).strip()
    if not raw:
        raise ValueError(f"Unknown instrument key: {key!r}")

    # Prefer InstrumentId form when it looks like one.
    if raw.count(":") == 3:
        return get_instrument_by_id(raw)

    from instruments.legacy import normalize_legacy_symbol

    return get_instrument(normalize_legacy_symbol(raw))
