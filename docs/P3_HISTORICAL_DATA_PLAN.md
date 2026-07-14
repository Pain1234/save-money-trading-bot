# P3 – Versioned Historical Market Data Plan

**GitHub Issue:** [#74](https://github.com/Pain1234/save-money-trading-bot/issues/74) — Plan and decompose P3 historical data pipeline

**Verified against main commit:** `b0ded96ea3b2813fc4acacebae02b5bc6882104c` (includes merge of PR #71)

**Evidence (repository paths):**

- `services/market_data/models.py`
- `services/market_data/repository.py`
- `services/market_data/runtime.py`
- `services/market_data/aggregation.py`
- `services/market_data/gaps.py`
- `services/market_data/stale.py`
- `services/market_data/validation.py`
- `services/market_data/ingest.py`
- `services/market_data/README.md`
- `docs/DECISION_LOG.md` (ADR-006)
- `tests/market_data/` (27+ test modules)

**Workflow:** Phase A (this document + Draft PR) → independent read-only review → Phase B (create GitHub sub-issues and update #45).

---

## 1. Ziel

Ein historischer Datenbestand, bei dem jedes Research-Ergebnis eindeutig beantworten kann:

- mit welchem Code,
- mit welcher Konfiguration,
- mit welchem unveränderlichen Datensatz,
- aus welcher Quelle,
- für welchen Zeitraum,
- mit welchen bekannten Datenproblemen.

---

## 2. Aktueller Zustand

| Capability | Status | Evidence |
|------------|--------|----------|
| Live/historical source (Hyperliquid HTTP/WS) | **Existing** | `providers/hyperliquid_*.py`, `runtime.py` |
| Raw data representation (`RawCandle`) | **Existing** | `models.py`, provider pipeline |
| Durable raw source capture | **Missing** | No persisted raw payload store |
| Raw dataset versioning | **Missing** | No manifest or `dataset_id` |
| Normalized candle model | **Existing** | `NormalizedCandle`, `CandleKey` |
| Normalized candle persistence | **Missing** | `InMemoryCandleRepository` only |
| Derived weekly/monthly (ISO from daily) | **Partial** | `aggregation.py`, ADR-006; native HL `1w` excluded |
| Symbol normalization | **Existing** | `symbols.py` fail-closed |
| UTC / closed-candle rules | **Existing** | `timeframes.py`, `closed.py` |
| Runtime backfill (730-day window) | **Partial** | `initial_backfill.py`, `runtime.py`; no batch CLI |
| In-process ingest idempotency | **Partial** | `repository.py` upsert; **lost on worker restart** |
| Gap detection logic | **Existing** | `gaps.py` |
| Duplicate/conflict detection | **Existing** | `validation.py`, `merge_policy.py`, `repository.py` |
| Stale transport/candle checks | **Existing** | `stale.py`, `live.py` |
| Fail-closed invalid ingest | **Existing** | `ingest.py`, `validation.py` |
| Dataset manifest / catalog | **Missing** | Only `MARKET_DATA_VERSION = "1.0"` constant |
| Research dataset binding | **Missing** | No experiment→dataset_id enforcement (P4) |
| Automated market_data tests | **Existing** | `tests/market_data/` |
| PostgreSQL candle tables | **Missing** | Alembic `001`–`009` have no candle tables |
| ARCHITECTURE.md accuracy (candle persistence) | **Partial** | Was incorrect; corrected in Phase A PR |

**Summary:** Ingestion, validation, gap/dup/stale **logic** is strong in-process; **durable, versioned, reproducible datasets** are the P3 gap.

---

## 3. Kanonischer Datenvertrag

Aligned with existing `NormalizedCandle` / `CandleKey` (`services/market_data/models.py`):

| Field | Rule |
|-------|------|
| Symbol | Internal symbol (`BTC`, `ETH`, `SOL`); provider mapping via `symbols.py` |
| Source | e.g. `hyperliquid` + network (`mainnet` / `testnet`) |
| Timeframe | `1D`, `1W`, `1M` (`MarketTimeframe`) |
| Timezone | UTC-aware only; naive timestamps rejected |
| Open time | Canonical UTC boundary per `timeframes.py` |
| Close time | Derived; closed iff `close_time <= evaluation_time` at query |
| OHLCV | Decimal; validated in `validation.py` |
| Quote volume / trade count | Optional; document if source provides |
| Finality | Query-time closure rule; persisted `is_closed` is metadata |
| Import timestamp | UTC; stored in manifest, excluded from content hash |
| Schema version | Manifest field; bump on breaking contract change |

**Layers:**

1. **Raw source capture** — immutable durable **provider payload** captured at import time (e.g. Hyperliquid `candleSnapshot` response bodies). Not a normalized re-export; normalized candles are a separate layer derived from a fixed raw artifact.
2. **Normalized candles** — canonical trading/research unit; deterministic given a fixed raw artifact + import config + code commit
3. **Derived aggregates** — ISO weekly/monthly from daily; parent dataset reference required
4. **Research datasets** — immutable manifest + catalog entry linking raw and normalized identities

---

## 4. Dataset-Identität

### Manifest fields (minimum)

`dataset_id`, `schema_version`, `source`, `symbols`, `timeframes`, `start_timestamp`, `end_timestamp`, `timezone`, `row_count`, `content_hash`, `raw_dataset_id`, `raw_content_hash`, `import_configuration`, `code_commit`, `created_at`, `parent_dataset_id`, `quality_status`, `known_issues`

### Content hash rules (required before implementation)

Manifest issue must define:

- [ ] Hash algorithm fixed (e.g. SHA-256)
- [ ] Canonical row ordering defined
- [ ] Canonical timestamp serialization (UTC ISO-8601 with fixed precision)
- [ ] Numeric precision and serialization defined (no `1` vs `1.0` drift)
- [ ] Mutable metadata excluded from content hash (`created_at`, import job id, etc.)
- [ ] Separate hashes for raw, normalized, and aggregate layers where applicable
- [ ] Same logical content produces identical hash cross-platform

### Immutability

- Published dataset versions are **never overwritten**
- Corrections create a **new** `dataset_id` / version with `parent_dataset_id`
- Invalidation sets `quality_status` without deleting history

---

## 5. Importvertrag

### Determinism contract

Reproducibility is defined on **frozen inputs**, not on live re-fetch from an external API:

```text
immutable raw_dataset_id (or raw artifact content hash)
  + import configuration
  + code commit
  -> normalized content hash
```

- **Not guaranteed:** `same live source + config + code commit -> same raw bytes`. Hyperliquid may correct history, paginate differently, or rate-limit; a new HTTP fetch is a new observation.
- **Guaranteed:** given a fixed raw artifact, normalization is deterministic; re-normalizing the same raw artifact with the same config and code yields the same normalized content hash.
- Each import that persists a new raw artifact receives a new `raw_dataset_id`; superseding corrections link via `parent_dataset_id`.
- A divergent re-fetch against the live API creates a **new raw version**; it does not overwrite an existing raw artifact.

### Operational requirements

- Idempotent: repeated normalization of the **same** raw artifact produces no duplicate normalized keys
- Resumable or safely restartable with auditable checkpoints (checkpoint references raw artifact, not live API cursor alone)
- Import parameters persisted in manifest; `raw_dataset_id` and provenance required
- Errors produce explicit dataset status (no silent correction)
- Reuses existing validation path (`ingest.py`) where possible; extends with persistence

**No standalone import CLI today** — P3 adds batch tooling atop `HyperliquidMarketDataRuntime` / backfill paths; raw capture is mandatory before normalization (Issue drafts 4 and 5).

---

## 6. Qualitätsregeln

Reuse existing detectors; P3 adds **dataset-scoped reports** and manifest integration:

| Rule | Existing code | P3 deliverable |
|------|---------------|----------------|
| Gap detection | `gaps.py` | Persisted gap report per dataset |
| Duplicate detection | `validation.py`, `repository.py` | Persisted dup/conflict report |
| Stale data | `stale.py`, `live.py` | Stale thresholds in manifest quality |
| OHLC plausibility | `validation.py` | Blockers vs warnings in quality status |
| Extreme moves | — | Warning only; never auto-delete |

---

## 7. Quarantäne

- **Blockers:** fail closed; dataset not available to research
- **Warnings:** recorded in manifest `known_issues`; research may proceed with explicit flag
- Quarantine reason stored; correction → new dataset version
- Prior invalid version remains auditable

---

## 8. Aggregation

- ISO weekly from daily per **ADR-006** (`aggregation.py`, `_refresh_iso_weekly`)
- Incomplete periods excluded (`aggregation.py::_aggregate_bucket`)
- Derived dataset manifest must reference `parent_dataset_id`
- P3 audit issue verifies no look-ahead and deterministic re-aggregation

---

## 9. Speicherstrategie

**Decision deferred** to dedicated ADR issue (Issue draft #3 below).

Options to evaluate (no final choice in Phase A):

| Option | Reproducibility | Immutability | Ops complexity |
|--------|-----------------|--------------|----------------|
| PostgreSQL (extend shared DB) | High | Medium (needs append-only discipline) | Medium; ties to backup/restore |
| Versioned files / object store | High | High | Medium; separate backup |
| Hybrid (PG index + file blobs) | High | High | Higher |

**ADR required before storage implementation.** See migration policy in Issue draft #4.

---

## 10. Security und Betrieb

- No secrets in manifests or dataset artifacts
- External API rate limits documented (Hyperliquid)
- Logging without raw credential leakage
- Storage growth and retention policy TBD in storage ADR
- Backup/restore dependency documented (R-009 partial; local drill complete per #71)

---

## 11. Issue-Zerlegung (Entwürfe — Phase B)

**Do not create these GitHub issues until Phase A plan PR is approved.**

### Issue draft 1 — Define canonical historical market data contract

- **Labels:** `type:documentation`, `area:data`, `area:research`
- **Migrationen:** none
- **Depends on:** Plan issue (Phase A)
- **Acceptance:** symbol/timezone/candle fields; raw layer = immutable provider payload only (not normalized re-export); raw vs normalized vs derived; compatibility with `models.py`; ADR candidates listed

### Issue draft 2 — Implement dataset manifest and version identifier

- **Labels:** `type:feature`, `area:data`, `status:needs-evidence`
- **Migrationen:** none (schema/spec only)
- **Depends on:** draft 1
- **Acceptance:** manifest schema; deterministic `dataset_id`; `raw_dataset_id` / `raw_content_hash` fields; **full hash canonicalization checklist** (section 4); validation tests; example manifest

### Issue draft 3 — Decide immutable dataset storage architecture

- **Labels:** `type:documentation`, `area:data`, `area:infrastructure`, `status:needs-decision`
- **Migrationen:** none (ADR/decision only)
- **Depends on:** draft 2
- **Acceptance:** ADR with options analysis; recommendation; backup/restore impact; no implementation

### Issue draft 4 — Implement immutable dataset storage and catalog

- **Labels:** `type:feature`, `area:data`, `area:infrastructure`
- **Migrationen:** allowed **only if** storage ADR selects PostgreSQL or hybrid — see migration policy below
- **Depends on:** draft 3
- **Acceptance:** append-only catalog; immutable **raw artifact store** with versioned or content-addressed identity; catalog links raw artifacts to normalized dataset manifests; no overwrite; invalid versions auditable; research lookup by `dataset_id`

### Issue draft 5 — Implement deterministic historical import and backfill

- **Labels:** `type:feature`, `area:data`
- **Depends on:** draft 4
- **Acceptance:** historical import **captures and persists raw provider payloads** before normalization; manifest records `raw_dataset_id`, fetch timestamp, source endpoint, and pagination metadata; repeatable normalization from fixed raw artifact; idempotent normalized keys; resumable checkpoints; live re-fetch creates new raw version (section 5); tests

### Issue draft 6 — Implement dataset quality validation and reports

- **Labels:** `type:feature`, `area:data`, `area:risk`
- **Depends on:** draft 5
- **Acceptance:** wraps `gaps.py`, `validation.py`, `stale.py`; gap/dup/stale/plausibility reports; manifest `quality_status`

### Issue draft 7 — Implement invalid dataset quarantine

- **Labels:** `type:feature`, `area:risk`, `area:research`
- **Depends on:** draft 6
- **Acceptance:** blockers prevent research use; warnings recorded; new version on fix

### Issue draft 8 — Verify deterministic timeframe aggregation

- **Labels:** `type:feature`, `area:data`, `area:research`
- **Depends on:** draft 5
- **Acceptance:** ADR-006 regression; ISO week boundaries; parent manifest link; no look-ahead

### Issue draft 9 — Complete P3 dataset reproducibility audit

- **Labels:** `type:operations`, `area:research`, `status:needs-evidence`
- **Depends on:** drafts 7, 8
- **Migrationen:** none
- **Acceptance:** double import hash match; quarantine case; all ROADMAP P3 exit criteria checked

### Migration policy (implementation issues only)

A database migration is permitted only when:

- the storage ADR selects PostgreSQL or hybrid storage,
- the migration is in scope of that specific issue,
- upgrade and rollback are documented,
- existing paper-trading tables are not unintentionally altered,
- integration tests are included.

**Explicit no-migration issues:** drafts 1, 2, 3, 9, and pure documentation/audit work.

---

## 12. Exit-Criteria-Mapping (ROADMAP P3)

| ROADMAP exit criterion | Responsible issue draft |
|------------------------|-------------------------|
| Each research dataset has manifest (hash, range, symbols, source) | 2 + 4 |
| Re-import produces identical aggregates for fixed version | 5 + 8 + 9 (re-normalize from same `raw_dataset_id`, not live re-fetch) |
| Gap/duplicate audit documented | 6 + 9 |

| R-001 acceptance (#45) | Issue draft |
|------------------------|-------------|
| Dataset-ID | 2 |
| Manifest with source/symbols/range/timezone/hash | 2 |
| Gap/duplicate detection | 6 |
| Stale threshold | 6 |
| Block/quarantine bad data | 7 |
| Re-import identical aggregates | 5, 8, 9 |
| Regression tests | 6, 8, 9 |

---

## 13. P2-Gate

See **ADR-012** in `docs/DECISION_LOG.md`.

- P2 operational train (#67–#72) and local backup/restore drill (#71 merged) provide the operational minimum for P3 work.
- **Issue #11** (Railway non-prod restore) remains open for full P2 completion but **does not block** P3 historical-data planning or implementation.
- P3 must not depend on untested Railway restore behavior.

**Phase A (this PR):** planning only — no P3 implementation.

**Phase B (after plan approval):** create sub-issues; update #45 child list with real issue numbers.

---

## Recommended order

1. Plan issue + this document (Phase A)
2. Issue draft 1 (contract)
3. Issue draft 2 (manifest + hash rules)
4. Issue draft 3 (storage ADR)
5. Issue draft 4 (storage + catalog)
6. Issue draft 5 (import/backfill)
7. Issue drafts 6 + 8 (parallel after 5)
8. Issue draft 7 (quarantine)
9. Issue draft 9 (audit)
