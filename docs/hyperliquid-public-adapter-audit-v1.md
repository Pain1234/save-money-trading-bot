# Hyperliquid Public Adapter Audit V1 — Remediation Report

Read-only audit findings remediated in `services/market_data/` and `tests/market_data/hyperliquid/`.

## Blockers Fixed

### B1 — Readiness at INCOMPLETE

**Before:** Only `INVALID` and `DISCONNECTED` blocked readiness; `INCOMPLETE` could yield `readiness=True`.

**After:** `readiness=True` requires every configured series to have `DataQualityStatus.VALID`. `INCOMPLETE`, `INVALID`, `DISCONNECTED`, and `STALE` all block readiness.

**Policy:** `VALID` is the only fully trade-ready status. `STALE` remains observable in series status but prevents orchestrator readiness until fresh data arrives.

### B2 — Silent partial pagination

**Before:** Hitting `max_pagination_pages` or stagnant timestamps could return partial history without error.

**After:** `HyperliquidPaginationIncompleteError` is raised when:
- `max_pagination_pages` exhausted while more data remains
- Last open timestamp repeats without progress (stagnant pages)

Partial results are never passed to `ingest_raw_batch`.

### B3 — Cold-start event loss

**Before:** `start()` called `connect_and_subscribe()` before `begin_buffer()`.

**After:** Startup order is:
1. `begin_buffer()`
2. Meta fetch
3. WebSocket connect + subscribe + ack
4. HTTP backfill per stream
5. `end_buffer()` + chronological replay via `ingest_live_raw`
6. Readiness evaluation

On failure: `discard_buffer()` and runtime error state reset.

## Critical Fixes

### C1 — Candle before subscription ack

**Before:** `_handle_candle` accepted messages for `_subscribed` streams before ack.

**After:**
- During active buffer (startup/reconnect): candles for subscribed streams are buffered even before ack
- Outside buffer: only `_acked_subs` streams are processed into the live queue

### C2 — Meta/backfill status

**Before:** `_meta_ok=True` could persist after backfill failure.

**After:**
- `_meta_ok`, `_backfill_ok`, `_initial_backfill_done` reset on any backfill failure
- `_last_error` records failure message
- Readiness requires `_meta_ok`, `_backfill_ok`, `_initial_backfill_done`, and `_last_error is None`

### C3 — Timeout/connection retry

**Before:** `HyperliquidTimeoutError` and `HyperliquidConnectionError` were not retried.

**After:** Both are retryable with bounded exponential backoff (same as 429/5xx). Parse errors and 4xx remain non-retryable. `CancelledError` is never caught.

## Medium Fixes

| ID | Fix |
|----|-----|
| M1 | Invalid `Retry-After` header falls back to backoff delay |
| M2 | Pydantic `Field` constraints on config; `for_network()` re-validates overrides |
| M3 | Candles with open before `startTime` are skipped; candles after `endTime` raise parse error |
| M4 | `process_live()` triggers controlled reconnect when WS status is `RECONNECTING`; reconnect lock prevents parallel reconnects |
| M5 | Background tasks cancelled and awaited on disconnect; idempotent shutdown |
| M6 | `_last_error` and WS `background_error` surfaced in runtime status |
| M7 | `validate_raw_candle` uses `Decimal.is_finite()` instead of float conversion |

## Pagination Completion Semantics

| Outcome | Behavior |
|---------|----------|
| Empty page | Complete (API end signal) |
| Last page `< max_candles_per_snapshot` | Complete |
| Last candle open ≥ endTime | Complete |
| Max pages with cursor < endTime | `HyperliquidPaginationIncompleteError` |
| Stagnant timestamp (2 pages) | `HyperliquidPaginationIncompleteError` |

## Readiness Rules (summary)

```
readiness = meta_ok
         AND backfill_ok
         AND initial_backfill_done
         AND all series VALID
         AND all subs acked
         AND ws CONNECTED
         AND no conflicts
         AND last_error is None
```

## Test Results (standard suite, no network)

```
296 passed, 4 skipped
mypy services: Success (61 files)
mypy hyperliquid tests: Success (6 files)
ruff: All checks passed
```

Live testnet smoke tests (2026-07-11): 4 passed in 3.54s.

FREIGEGEBEN FÜR PAPER-TRADING-ORCHESTRATOR

## Remaining Model Assumptions

- Meta `type=meta` returns perpetual universe (no explicit spot/perp discriminator)
- Duplicate coin names in meta collapse via set semantics
- `STALE` blocks readiness; orchestrator may choose degraded policies explicitly
- Hyperliquid may return snapshot candles with open before `startTime`; these are skipped
