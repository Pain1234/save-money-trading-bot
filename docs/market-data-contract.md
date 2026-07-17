# Canonical Historical Market Data Contract

**Issue:** #76
**Parent plan:** [P3_HISTORICAL_DATA_PLAN.md](P3_HISTORICAL_DATA_PLAN.md)
**Epic:** #45 (R-001)

This document is the normative contract for versioned historical market datasets in P3. Implementation issues (#77–#84) must conform to it.

---

## 1. Data layers

| Layer | Definition | Mutable | Persistence (P3 target) |
|-------|------------|---------|---------------------------|
| **Raw source capture** | Immutable provider payload bytes captured at import time (e.g. Hyperliquid `candleSnapshot` JSON response bodies per page). **Not** a normalized re-export. | Never overwrite; new fetch → new raw version | Raw artifact store (#79) |
| **Normalized candles** | Validated internal candles after `normalize.py` + `ingest.py`; canonical research/trading unit. | Append-only per dataset version | Catalog + normalized store (#79) |
| **Derived aggregates** | ISO weekly/monthly from daily per ADR-006 (`aggregation.py`). | Append-only; references parent | Derived dataset manifest (#77, #83) |
| **Research dataset** | Immutable manifest + catalog entry linking raw, normalized, and derived identities. | Published versions never overwritten | Dataset catalog (#79) |

```text
Provider HTTP/WS payload (raw bytes)
  -> normalize + validate (ingest.py)
  -> NormalizedCandle rows
  -> optional derive weekly/monthly (aggregation.py)
  -> StrategyDataBundle (runtime query only today)
```

---

## 2. Normalized candle field contract

Aligned with `NormalizedCandle`, `CandleKey`, and `RawCandle` in `services/market_data/models.py`.

| Field | Type / rule | Code reference |
|-------|-------------|----------------|
| `symbol` | `MarketSymbol`: `BTC`, `ETH`, `SOL` | `models.MarketSymbol` |
| `timeframe` | `MarketTimeframe`: `1D`, `1W`, `1M` | `models.MarketTimeframe` |
| `open_time` | UTC-aware; canonical boundary | `timeframes.py` |
| `close_time` | UTC-aware; derived from timeframe | `timeframes.py` |
| `open`, `high`, `low`, `close`, `volume` | `Decimal`; OHLCV validated | `validation.py` |
| `is_closed` | `bool`; metadata only at query time | `closed.py` |
| Provider symbol (raw only) | `provider_symbol` on `RawCandle` | `symbols.py` mapping |

### Query-time closure (normative)

- **Closed candle:** `close_time <= evaluation_time` (recomputed at query; not gated by persisted `is_closed` alone).
- Naive datetimes are rejected.
- All timestamps UTC.

### Source identity

- `source`: provider id + network, e.g. `hyperliquid/mainnet`, `hyperliquid/testnet`.
- Symbol mapping is fail-closed via `symbols.py`.

### Optional fields (document when present)

- Quote volume, trade count — include in manifest when source provides; omit from hash when absent across all rows.

---

## 3. Raw layer contract

| Rule | Detail |
|------|--------|
| Content | Opaque provider payload as received (JSON bytes for Hyperliquid HTTP pages). |
| Immutability | Once stored under a `raw_dataset_id`, bytes never change. |
| Re-fetch | Live API re-fetch creates a **new** `raw_dataset_id`; never overwrites. |
| Provenance | Manifest records fetch timestamp, endpoint, pagination metadata (#80). |
| Not raw | Normalized CSV/Parquet export, in-memory `RawCandle` tuples without original payload. |

---

## 4. Derived layer contract

| Rule | Detail |
|------|--------|
| Weekly | ISO week from daily only (ADR-006); native Hyperliquid `1w` subscription excluded. |
| Monthly | From complete daily buckets only (`aggregation.py::_aggregate_bucket`). |
| Parent link | Derived manifest **must** include `parent_dataset_id` pointing at daily normalized dataset. |
| Incomplete periods | Excluded from published derived dataset. |

---

## 5. Determinism contract

Reproducibility is defined on **frozen inputs**, not live re-fetch:

```text
immutable raw_dataset_id (or raw artifact content hash)
  + import_configuration
  + code_commit
  -> normalized content_hash
```

| Guaranteed | Not guaranteed |
|------------|----------------|
| Same raw artifact + config + code → same normalized hash | Same live source + config + code → same raw bytes |
| Re-normalization idempotent on candle keys | Exchange history corrections |
| | Pagination / rate-limit differences on re-fetch |

Corrections publish a new `dataset_id` with `parent_dataset_id`. Invalidation updates `quality_status` only.

---

## 6. Mapping to existing runtime types

| Contract concept | Current code | P3 gap |
|------------------|--------------|--------|
| Raw capture | `RawCandle` (in-memory parse result) | Durable payload store |
| Normalized candle | `NormalizedCandle` | Durable repository |
| Candle key | `CandleKey` | Same; used for idempotent upsert |
| Quality (runtime) | `DataQualityReport`, `DataQualityStatus` | Per-dataset persisted reports (#81) |
| Gaps / conflicts | `CandleGap`, `CandleConflict` | Dataset-scoped reports (#81) |
| Strategy output | `StrategyDataBundle` | Bound to `dataset_id` (P4) |
| In-memory store | `InMemoryCandleRepository` | Versioned catalog (#79) |

Existing enums **`DataQualityStatus`** (`VALID`, `STALE`, `INCOMPLETE`, `INVALID`, `DISCONNECTED`) remain the runtime vocabulary. Dataset manifest `quality_status` (#77) extends this for published datasets.

---

## 7. ADR candidates (not decided in this issue)

| Topic | Suggested ADR | Owner issue |
|-------|---------------|-------------|
| Immutable storage backend (PostgreSQL vs artifact store vs hybrid) | ADR-013 | #78 |
| Hash canonicalization (algorithm, row order, decimal serialization) | Part of manifest spec or ADR if contested | #77 |
| Retention / growth policy for raw artifacts | ADR-014 (future) | Post-P3 ops |
| Research experiment → `dataset_id` binding | P4 scope | Out of P3 |

---

## 8. Compatibility rules

1. **No breaking change** to `NormalizedCandle` / `CandleKey` field names without `schema_version` bump in manifest.
2. P3 persistence **adds** catalog and stores; it does not change paper-trading tables.
3. Runtime ingest path (`ingest.py`) remains the validation gate for normalized candles.
4. `MARKET_DATA_VERSION` constant may remain for service semver; dataset identity uses manifest `dataset_id` (#77).

---

## 9. Acceptance traceability (#76)

- [x] Symbol, timezone, candle fields documented
- [x] Raw layer = immutable provider payload only
- [x] Raw vs normalized vs derived documented
- [x] Compatibility with `models.py` explicit (section 6)
- [x] ADR candidates listed (section 7)
