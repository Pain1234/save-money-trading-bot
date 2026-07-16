# Canonical instrument model (P4.1 / Issue #128)

**Status:** Additive identity layer for P4 universe research  
**Issue:** [#128](https://github.com/Pain1234/save-money-trading-bot/issues/128)  
**Depends on:** P4.0 production baseline freeze ([#127](https://github.com/Pain1234/save-money-trading-bot/issues/127))

## Purpose

P4 needs a stable instrument identity beyond free-form symbol strings, without
changing BTC/ETH/SOL paper-trading behavior from the P2.5 baseline.

This package introduces:

| Type | Role |
|------|------|
| `InstrumentId` | Stable canonical id string (`venue:network:type:BASE`) |
| `Venue`, `Network`, `InstrumentType`, `AssetClass` | Explicit classification enums |
| `Instrument` | Frozen pydantic identity model |
| Registry | Production Hyperliquid perpetual universe: **BTC, ETH, SOL** |
| Legacy bridge | Map `"BTC"` / aliases / `MarketSymbol` ↔ `InstrumentId` |

## Package layout

```
services/instruments/
  __init__.py      # public API
  enums.py         # Venue, Network, InstrumentType, AssetClass
  identity.py      # InstrumentId, Instrument, make/parse helpers
  registry.py      # BTC/ETH/SOL registry + lookup
  legacy.py        # MarketSymbol / str compatibility
```

Import via `from instruments import ...` (`services/` is on pytest/`pythonpath`).

## InstrumentId format

```
{venue}:{network}:{instrument_type}:{BASE}
```

Example: `hyperliquid:mainnet:perpetual:BTC`

Ids are system-owned (not Hyperliquid coin indexes or other provider-internal keys).

## Production registry

Exactly three **active** instruments:

- Hyperliquid / mainnet / perpetual / crypto — BTC, ETH, SOL

No additional markets (e.g. HYPE) are activated here. Unknown keys fail closed.

## Legacy bridge (no P2.5 behavior change)

`MarketSymbol` remains the live market-data / paper-trading enum. Bridges:

- `resolve_legacy_symbol("BTC" | "ETH-USD" | MarketSymbol.BTC)` → `Instrument`
- `to_market_symbol(instrument | InstrumentId | "SOLUSDT")` → `MarketSymbol`
- Aliases aligned with `market_data.symbols`: bare, `-USD`, and `USDT` forms

**This commit is additive only:** candle semantics, backfill, strategy, risk, and
paper trading paths are unchanged. Wiring adapters to `InstrumentId` is deferred
to follow-on issues (#129+).

## Tests

```bash
python -m pytest tests/instruments/ -v
```
