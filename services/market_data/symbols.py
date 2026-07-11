"""Symbol mapping between providers and internal MarketSymbol."""

from __future__ import annotations

from market_data.models import MarketDataReasonCode, MarketSymbol

HYPERLIQUID_PROVIDER_SYMBOLS: dict[MarketSymbol, str] = {
    MarketSymbol.BTC: "BTC",
    MarketSymbol.ETH: "ETH",
    MarketSymbol.SOL: "SOL",
}

PROVIDER_TO_INTERNAL: dict[str, MarketSymbol] = {
    provider: internal for internal, provider in HYPERLIQUID_PROVIDER_SYMBOLS.items()
}

# Alternate provider aliases (fail-closed for unknown)
PROVIDER_TO_INTERNAL.update(
    {
        "BTC-USD": MarketSymbol.BTC,
        "ETH-USD": MarketSymbol.ETH,
        "SOL-USD": MarketSymbol.SOL,
        "BTCUSDT": MarketSymbol.BTC,
        "ETHUSDT": MarketSymbol.ETH,
        "SOLUSDT": MarketSymbol.SOL,
    }
)


def resolve_internal_symbol(provider_symbol: str) -> MarketSymbol:
    """Map provider symbol to internal symbol; fail-closed on unknown."""
    normalized = provider_symbol.strip().upper()
    if normalized in PROVIDER_TO_INTERNAL:
        return PROVIDER_TO_INTERNAL[normalized]
    if normalized in {s.value for s in MarketSymbol}:
        return MarketSymbol(normalized)
    raise ValueError(
        f"Unknown provider symbol: {provider_symbol!r} "
        f"(code={MarketDataReasonCode.MD_UNKNOWN_SYMBOL.value})"
    )


def to_provider_symbol(symbol: MarketSymbol, *, provider: str = "hyperliquid") -> str:
    if provider == "hyperliquid":
        return HYPERLIQUID_PROVIDER_SYMBOLS[symbol]
    raise ValueError(f"Unsupported provider: {provider}")
