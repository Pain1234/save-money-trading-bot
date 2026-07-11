# Market Data Service V1

Read-only market data layer for **BTC**, **ETH**, and **SOL**. Validates historical and live candles and exposes closed, look-ahead-safe bundles for the Strategy Engine.

No wallet, orders, private APIs, or trading logic.

## Architecture

| Module | Role |
|--------|------|
| `models.py` | Typed domain models (`NormalizedCandle`, `StrategyDataBundle`, …) |
| `symbols.py` | Provider ↔ internal symbol mapping (fail-closed) |
| `timeframes.py` | UTC boundaries, close times, closed-candle rule |
| `validation.py` | OHLCV and series validation |
| `ingest.py` | Shared validate-before-persist ingest path |
| `merge_policy.py` | Native vs aggregated weekly/monthly reconciliation |
| `stale.py` | Timeframe-aware candle staleness |
| `normalize.py` | Raw → normalized conversion |
| `closed.py` | Closed-candle filtering |
| `aggregation.py` | Weekly/monthly from daily |
| `gaps.py` | Missing candle detection |
| `repository.py` | In-memory `CandleRepository` |
| `providers/` | Historical, live, backfill, Hyperliquid parser |
| `bundle.py` | `get_strategy_bundle()` |
| `service.py` | `MarketDataService` orchestration |
| `live.py` | Live feed, stale detection, reconnect |
| `runtime.py` | `HyperliquidMarketDataRuntime` orchestration |
| `config.py` | Mainnet/testnet typed configuration |
| `network/` | Async HTTP, WebSocket, retry, Decimal JSON |

## Data Flow

```
Provider (RawCandle)
  → validate_raw_candle
  → normalize
  → ingest_normalized (validate_candle_structure)
  → repository.upsert (idempotent / conflict)
  → gap detect → backfill (optional)
  → merge native + aggregated weekly/monthly
  → filter closed (close_time <= evaluation_time)
  → StrategyDataBundle (strategy_engine.CandleSeries)
```

## UTC Rules

- All timestamps are **timezone-aware UTC**.
- Pure query functions never call `datetime.now()`.
- **Closed candle:** `close_time <= evaluation_time` (recomputed at query time).
- The persisted `is_closed` flag is metadata only — not a query gate.
- Evaluation exactly at `close_time` is allowed.

## Closure Semantics

`get_closed_before` and `filter_closed_candles` use only `is_candle_closed(close_time, evaluation_time)`. A candle ingested as open becomes queryable automatically once `evaluation_time` reaches its `close_time`, without re-ingest.

## Native / Aggregation Policy (Weekly & Monthly)

1. Load native closed candles from the repository.
2. Independently aggregate from complete daily periods when sufficient daily data exists.
3. Merge by `open_time`:
   - missing period → use aggregate
   - identical OHLCV → accept (no conflict)
   - differing OHLCV → `MD_DUPLICATE_CONFLICT`, bundle INVALID
4. Incomplete aggregated periods are never published.
5. Result is chronologically sorted and duplicate-free.

## Ingest Validation

All paths (`ingest_raw`, `store_normalized`, backfill, live) use `ingest_normalized`:

- Invalid OHLC, NaN, Infinity, negative volume → **not persisted**
- Machine-readable reason codes returned
- Repository unchanged on reject

## Live Deduplication

- Key = `(provider_symbol, timeframe, open_time)`
- Identical replay → idempotent skip, emits `MD_DUPLICATE_IDENTICAL`
- Conflicting replay → repository conflict, existing candle preserved
- Invalid payloads rejected before persist

## Stale Semantics

- **Transport stale:** heartbeat threshold exceeded (`is_transport_stale`)
- **Candle stale:** expected next period closed without a newer candle (`is_candle_data_stale`)
- Daily data is not candle-stale during an ongoing UTC day

## Hyperliquid Parser

- Required fields: `s`, `t`, `T`, `o`, `h`, `l`, `c`
- Timestamps ≥ 1e12 → milliseconds; ≥ 1e9 → seconds; otherwise rejected
- `closed` defaults to **False** when omitted
- NaN/Infinity strings rejected; Decimal parsed directly from strings
- `t` = open time, `T` = close time (UTC)

## Timeframes

Same values as Strategy Engine: `1D`, `1W`, `1M`.

| Timeframe | Open | Close |
|-----------|------|-------|
| Daily | 00:00 UTC | 23:59:59 UTC same day |
| Weekly | Monday 00:00 UTC | Sunday 23:59:59 UTC |
| Monthly | 1st 00:00 UTC | last second of month |

Incomplete weeks/months are **not** published when aggregating from daily.

## Data Quality Status

| Status | Meaning |
|--------|---------|
| `VALID` | Usable for strategy |
| `STALE` | Transport or candle staleness |
| `INCOMPLETE` | Gaps or insufficient history |
| `INVALID` | OHLC errors, conflicts, future candles |
| `DISCONNECTED` | Live feed not connected |

Reason codes: `MD_VALID`, `MD_STALE`, `MD_GAP_DETECTED`, `MD_BACKFILL_FAILED`, `MD_DUPLICATE_CONFLICT`, `MD_DUPLICATE_IDENTICAL`, …

## Look-ahead Protection

- Open candles excluded at query time
- Future candles excluded
- Weekly/monthly only after period close
- Strategy bundle never contains `close_time > evaluation_time`

## Public API

```python
from datetime import UTC, datetime
from market_data import (
    MarketDataService,
    MarketSymbol,
    InMemoryCandleRepository,
    get_strategy_bundle,
)

repo = InMemoryCandleRepository()
service = MarketDataService(repo)
# … ingest normalized or raw candles …
bundle = get_strategy_bundle(
    repo,
    MarketSymbol.BTC,
    datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC),
    daily_minimum=21,
    weekly_minimum=50,
    monthly_minimum=20,
)
assert bundle.is_usable  # only when report.status == VALID
```

## Tests

```bash
pytest tests/strategy_engine tests/risk_engine tests/backtester tests/market_data -q
mypy services/strategy_engine services/risk_engine services/backtester services/market_data
ruff check services/market_data tests/market_data
```

## Model Assumptions

1. Daily close at 23:59:59 UTC (matches Strategy Engine test conventions).
2. Weekly/monthly aggregation requires **complete** periods only.
3. No synthetic gap filling — backfill must supply real candles.
4. In-memory repository only in V1 (no PostgreSQL yet).
5. Hyperliquid public adapter: async HTTP + WebSocket (see [Hyperliquid Adapter V1](../../docs/hyperliquid-public-adapter-v1.md)).

## Hyperliquid Public Adapter

- **HTTP:** `POST /info` for `meta` and `candleSnapshot` with pagination
- **WebSocket:** 9 candle subscriptions (BTC/ETH/SOL × 1d/1w/1M), ping/pong, ack-gated CONNECTED
- **Config:** `HyperliquidPublicConfig.from_env()` or `for_network(MAINNET|TESTNET)`
- **Runtime:** `HyperliquidMarketDataRuntime.backfill_symbol()` uses shared ingest path
- **Live smoke:** `RUN_HYPERLIQUID_LIVE_TESTS=1 pytest -m live`
- **Limit:** ~5000 candles per snapshot; volume in base unit; no `closed` field — closure from `T`

See also: [Market Data Audit V1 Report](../../docs/market-data-audit-v1.md).
