# Issue #121 baseline (pre-change)

**Status:** documented before any production change
**Date:** 2026-07-15
**main SHA:** `ad702863c01aaa99f5243228ba258497d0dc3a0e` (PR #120 merge)
**API deploy SHA (verified):** `ad702863c01aaa99f5243228ba258497d0dc3a0e`

## Regions (`RAILWAY_REPLICA_REGION` via SSH)

| Service | Region | Replicas |
|---------|--------|----------|
| `paper-trading-api` | **`sfo`** | 1 (default / non-multi explicit) |
| `paper-trading-dashboard` | **`europe-west4-drams3a`** | 1 |
| `paper-trading-postgres` | **`europe-west4-drams3a`** | 1 |
| `paper-trading-worker` | (not required for Layer C) | 1 |

Private API URL (dashboard): `http://paper-trading-api.railway.internal:8080`
(No secrets recorded.)

## Code-path finding (MEASURED by code review)

`services/paper_trading/api_dependencies.py` → `get_db_session`:

1. `create_db_engine(...)` **per request**
2. `create_session_factory(engine)` **per request**
3. attach cursor listeners
4. `engine.dispose()` in `finally` **per request**

This forces fresh pool/connection setup on every HTTP request. Combined with API in `sfo` and Postgres in `europe-west4-drams3a`, the ~2.13 s residual is **consistent with cross-region connect + setup**, not SQL execution (Layer D sub-ms).

Region attribution remains a **hypothesis** until a one-factor before/after.

## Hypotheses (ranked)

1. **H1 Region mismatch** (API sfo vs DB EU) — preferred first infra experiment
2. **H2 Per-request engine/dispose** — code path confirmed; share unknown until timing breakdown or post-region remeasure
3. **H3 Middleware/serialization** — unlikely sole cause for flat ~2.13 s across body sizes

## Experiment 1 (single factor)

Change **only** `paper-trading-api` region: `sfo` → `eu-west` (`europe-west4-drams3a`).
No schema, TTL, index, strategy, or pooling change in the same window.

Rollback: `railway scale --service paper-trading-api us-west=1 eu-west=0` (or restore previous multi-region config).

## Artifacts

| File | Role |
|------|------|
| `docs/operations/dashboard-layer-c-before-121.json` | Before region move |
| `docs/operations/dashboard-layer-c-after-121.json` | After region move |
| `docs/operations/dashboard-fastapi-residual-121.md` | Decision write-up |
