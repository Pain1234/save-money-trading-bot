# Market Data Service V1 — Audit Remediation Report

## Executive Summary

This report documents the remediation of all confirmed findings from the read-only Market Data V1 correctness and look-ahead audit. Fixes were applied exclusively within `services/market_data/` and `tests/market_data/` using test-driven development: each production change was preceded by a failing regression test.

After remediation, **268 tests pass**, **mypy reports no issues** across core services, and **ruff is clean** for market data code. No changes were made to strategy engine, risk engine, backtester, frozen specifications, dashboard, or infrastructure.

## Confirmed Errors (Audit)

### Critical

| ID | Finding |
|----|---------|
| C1 | Single native weekly candle blocked daily aggregation fallback for weekly minimum |
| C2 | `get_closed_before` gated on persisted `is_closed`, excluding later-valid candles |
| C3 | Conflicts filtered by timeframe only — ETH conflict invalidated BTC bundle |
| C4 | `ingest_raw` / `store_normalized` upserted without pre-persist validation |
| C5 | Live dedup by key only hid conflicts; invalid payloads could reach normalize |
| C6 | Native weekly/monthly silently preferred over aggregates; no reconciliation |

### Medium

| ID | Finding |
|----|---------|
| M1 | Heartbeat-only stale detection; no timeframe-aware candle staleness |
| M2 | Backfill failure replaced `MD_GAP_DETECTED` with `MD_BACKFILL_FAILED` |
| M3 | Backfill accepted wrong symbol/timeframe gap fills |
| M4/M5 | Inconsistent UTC normalization and closed filtering |
| M6 | Overlapping intervals not explicitly rejected |
| M7 | Hyperliquid parser: silent ms/s assumption, default `closed=True`, weak validation |
| M8 | Reconnect backfilled daily only; no backoff reset; shutdown incomplete |
| M9 | `MD_DUPLICATE_IDENTICAL` declared but never emitted |
| M10 | Non-finite volume coded as `MD_INVALID_OHLC` |

## Minimal Fixes Applied

| Area | Fix |
|------|-----|
| Closure | Query-time `is_candle_closed(close_time, eval_time)` only; removed `is_closed` gate |
| Conflicts | `_conflicts_for(symbol, timeframe)` in bundle assembly |
| Ingest | New `ingest.py` with `validate_candle_structure` + `validate_raw_candle` before upsert |
| Live | Full-candle compare on key collision; raw validation; conflict not hidden by cache |
| Merge | New `merge_policy.py` — native + aggregate merge with explicit conflict detection |
| Stale | New `stale.py` — transport vs candle staleness separated |
| Backfill | Preserve `MD_GAP_DETECTED`; append `MD_BACKFILL_FAILED`; symbol/TF filter |
| Hyperliquid | Epoch unit detection, `closed` default False, NaN/Inf rejection, Decimal from strings |
| Reconnect | Backfill daily/weekly/monthly; backoff reset on connect; shutdown blocks processing |
| Volume | Non-finite volume → `MD_INVALID_VOLUME` |

## New Regression Tests

| File | Coverage |
|------|----------|
| `test_audit_closure.py` | C2 query-time closure |
| `test_audit_cross_symbol.py` | C3 symbol-scoped conflicts |
| `test_audit_ingest_validation.py` | C4 pre-persist validation |
| `test_audit_live_dedup.py` | C5 live idempotency and conflicts |
| `test_audit_native_merge.py` | C1/C6 native/aggregation policy |
| `test_audit_medium.py` | M1–M10 medium fixes |
| `test_audit_reference.py` | Hand-calculated reference cases and no-lookahead property |

## Native / Aggregation Policy

1. Load native closed candles from repository.
2. Aggregate independently from complete daily data.
3. Merge by `open_time`: supplement missing periods; accept identical OHLCV; conflict on mismatch.
4. Conflicting sources → bundle `INVALID` with `MD_DUPLICATE_CONFLICT`.
5. Incomplete aggregated periods excluded.
6. Chronological, duplicate-free output.

## Closure Semantics

Usability at query time is determined solely by `close_time <= evaluation_time`. Persisted `is_closed` is metadata for provider state and does not permanently exclude candles that have since closed relative to a later `evaluation_time`.

## Live Deduplication

Identical key + identical OHLCV → idempotent skip (`MD_DUPLICATE_IDENTICAL`). Identical key + differing OHLCV → repository conflict, no overwrite. Invalid raw payloads rejected before normalization.

## Stale Semantics

- **Transport stale:** no heartbeat within threshold.
- **Candle stale:** next expected period has closed without a newer candle arriving.
- Ongoing daily UTC period is not candle-stale.

## Hyperliquid Parser Semantics

- `t` = open epoch, `T` = close epoch (UTC after conversion).
- ≥ 1e12 → milliseconds; ≥ 1e9 → seconds; else error.
- Missing `closed` → `False`.
- Required fields enforced; NaN/Infinity strings rejected.

## Remaining Specification Gaps

1. Persisted repository schema and retention policy undefined.
2. Real-time Hyperliquid HTTP/WebSocket integration not in V1 scope.
3. Configurable stale thresholds per environment not specified.
4. Cross-exchange candle boundary normalization rules not fully specified.
5. PostgreSQL repository implementation deferred.

## Test Results

```
pytest tests/strategy_engine tests/risk_engine tests/backtester tests/market_data -q
268 passed

mypy services/strategy_engine services/risk_engine services/backtester services/market_data
Success: no issues found in 49 source files

ruff check services/market_data tests/market_data
All checks passed
```

## Freigabeempfehlung

All confirmed critical and medium audit findings within scope have been remediated with regression test coverage. Look-ahead safety is enforced at query time. Cross-symbol conflict isolation, ingest validation, native/aggregation reconciliation, and live deduplication behave as specified.

FREIGEGEBEN FÜR PAPER-TRADING-SIGNALPIPELINE
