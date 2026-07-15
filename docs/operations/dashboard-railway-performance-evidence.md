# Railway dashboard performance evidence (Issue #101)

**Date:** 2026-07-15  
**Project:** `graceful-compassion` / environment `production`  
**Deployed Git SHA (main after #119):** `32a94384504fd35ee19ac077799a5c135b4b4aaf`  
**Method:** Harnesses from PR #119 via `railway ssh` (private hop) + public URL probes

## Environment (measured)

| Service | Region | Role in measurement |
|---------|--------|---------------------|
| `paper-trading-dashboard` | **EU West** | Public HTTPS `https://bot.save-money.xyz`; Layer C probe origin |
| `paper-trading-api` | **sfo** | Private `paper-trading-api.railway.internal:8080`; Layer D EXPLAIN host |
| `paper-trading-postgres` | **EU West** | `postgres.railway.internal` |
| `paper-trading-worker` | EU West | Not exercised |

**Finding (architecture):** Dashboard and Postgres are in EU West; the read-only API is in **sfo**. The private Next.js → FastAPI path therefore crosses regions, and API → Postgres also crosses regions. This dominates route latency far more than SQL plans on current table sizes.

Private API was **not** made public. Layer C used SSH into the dashboard service.

## Artifacts

| Layer | Artifact | Status |
|-------|----------|--------|
| A Browser usable content | — | `NOT_MEASURED` — needs `PAPER_DASHBOARD_USER` / `PAPER_DASHBOARD_PASSWORD` |
| B Next.js SSR (authenticated) | — | `NOT_MEASURED` — same credentials |
| B public `/login` only | [`dashboard-layer-b-ssr-railway-login-partial.json`](dashboard-layer-b-ssr-railway-login-partial.json) | `PARTIAL` |
| C FastAPI private hop | [`dashboard-layer-c-api-railway.json`](dashboard-layer-c-api-railway.json) | `MEASURED` |
| D PostgreSQL EXPLAIN | [`dashboard-layer-d-explain-railway.json`](dashboard-layer-d-explain-railway.json) | `MEASURED` (empty history tables: no cursor page) |

Probe helper (dashboard Node): `scripts/railway_layer_c_probe.js`

---

## Layer B — public login SSR (`PARTIAL`)

Unauthenticated `GET https://bot.save-money.xyz/login`, warm n=8:

| Metric | Value |
|--------|------:|
| TTFB p95 | **187.4 ms** |
| HTML bytes p50 | 6222 |

Authenticated dashboard routes remain `NOT_MEASURED` until dashboard credentials are supplied to the Layer A/B harnesses.

---

## Layer C — FastAPI via private Next.js→API hop (`MEASURED`)

Probe service: `paper-trading-dashboard` → `http://paper-trading-api.railway.internal:8080`  
Warm runs: 5 (after 1 discarded warm-up). All routes `MEASURED` with full `X-Perf-*` headers.

| Route | Client p95 (ms) | API total p95 (ms) | DB p95 (ms) | Queries p95 | Bytes p50 | Events payload share |
|-------|----------------:|-------------------:|------------:|------------:|----------:|---------------------:|
| status | 3249 | 2829 | 700.2 | 4 | 639 | — |
| dashboard_summary | 3313 | 3165 | 981.5 | 6 | 1175 | — |
| wallet | 2552 | 2405 | 279.1 | 1 | 238 | — |
| positions | 2646 | 2497 | 280.6 | 1 | 42 | — |
| orders | 2556 | 2406 | 279.6 | 1 | 42 | — |
| fills | 2561 | 2405 | 280.7 | 1 | 42 | — |
| equity | 2561 | 2403 | 279.7 | 1 | 1210 | — |
| events | 2695 | 2405 | 279.3 | 1 | **15191** | **0.172** |
| scheduler_runs | 2844 | 2546 | 418.1 | 1 | **17119** | — |

Interpretation:

- Every monitored API call is **already ~2.4–3.3 s** before browser paint — **above** the ROADMAP 1.5 s usable-content budget on the API hop alone.
- `db_ms` (~280 ms single-query pages; up to ~981 ms on summary) is elevated vs local baselines, consistent with **API(sfo) → Postgres(EU)**.
- Large residual `total_ms − db_ms` suggests non-cursor cost (e.g. per-request engine/connect across region); not inventing causes beyond region mismatch without deeper APM.
- `/events` payload_json share ≈ **17%** of response bytes on this dataset — notable but **not** the majority of the 15 KB body; list projection remains an `OPTIMIZATION_CANDIDATE`, not the #1 cross-region issue.

---

## Layer D — PostgreSQL EXPLAIN (`MEASURED`)

Host: SSH `paper-trading-api` with `SET TRANSACTION READ ONLY` + `SET LOCAL statement_timeout`.  
URL driver normalized to `postgresql+psycopg://`.

| Route | Rows exact | First page | Cursor page | First exec ms | Plan notes |
|-------|-----------:|------------|-------------|--------------:|------------|
| /fills | 0 | MEASURED | NOT_MEASURED (empty) | 0.043 | Limit+Sort+Seq Scan (empty) |
| /orders | 0 | MEASURED | NOT_MEASURED (empty) | 0.031 | Limit+Sort+Seq Scan (empty) |
| /positions | 0 | MEASURED | NOT_MEASURED (empty) | 0.027 | Limit+Sort+Seq Scan (empty) |
| /equity | 4 | MEASURED | NOT_MEASURED (<100 rows) | 0.042 | Limit+Sort; hit=1 |
| /events | **437** | MEASURED | **MEASURED** | 0.074 / 0.087 | Limit+Sort quicksort; hit=7 |
| /scheduler-runs | **310** | MEASURED | **MEASURED** | 0.124 / 0.186 | Limit+Sort top-N; hit=7 |

Index conclusion from this environment:

- SQL execution is **sub-millisecond**. No index migration is justified from these plans.
- Seq Scan on empty or tiny tables is `NO_ACTION` under the evidence gate.
- History growth (events/scheduler ~300–400 rows) is not the current user-visible bottleneck.

---

## Top-3 bottlenecks (scored from Railway samples)

1. **Cross-region service placement (API in sfo vs Postgres/Dashboard in EU West)**  
   Dominates API `total_ms` and private-hop client p95 (~2.5–3.3 s). Call frequency: every dashboard page.
2. **`GET /api/v1/dashboard-summary`**  
   Highest API total/db/query_count (p95 total 3165 ms, db 981 ms, 6 queries) — Overview path.
3. **Large history JSON (`/events`, `/scheduler-runs`)**  
   15–17 KB responses; events `payload_json` share ≈17%. Secondary to region latency; still an optimization candidate for SSR/browser transfer.

Hypothesis “Incidents slow mainly due to payload_json” is **only partly supported**: payload is a minority share today; region latency dominates.

---

## Cache recommendations (from these values only)

| Data class | Recommendation | Reason |
|------------|----------------|--------|
| Readiness / status / summary | Keep **1–2 s** (or no-store for forced refresh) | Critical, but 2 s cache cannot hide 2.5 s origin without becoming stale-looking; fix region first |
| Wallet / positions | **3–5 s** remain plausible | Origin ~2.5 s; short TTL avoids stampede without long staleness |
| Orders / fills | **3–5 s** | Same; tables currently empty in prod DB evidence |
| Equity / events / scheduler | **15–30 s** remains reasonable | Already 30 s on API; not primary latency driver vs region |

Do **not** treat longer TTLs as a substitute for co-locating API with Postgres.

---

## Index candidates

| Candidate | Decision |
|-----------|----------|
| All composite history indexes from checklist | **`NO_ACTION` / deferred** — EXPLAIN exec ≪ 1 ms; no before/after benefit expected vs 2.5 s network |
| Co-locate `paper-trading-api` to EU West (ops) | **`FOLLOW_UP_REQUIRED`** — highest impact; not an Alembic change |
| Lightweight `/events` projection | **`OPTIMIZATION_CANDIDATE`** — separate feature issue after region fix |
| Speculative index migration ticket | **Not opened** — evidence package for indexes not met |

---

## Still open for closing Issue #101

- [ ] Layer A authenticated browser timings (needs dashboard password in env)
- [ ] Layer B authenticated SSR TTFB for Overview/Status/… 
- [ ] Confirm hard-nav LCP non-null on Railway once A runs
- [ ] Re-measure Layer C after API region co-location (before/after)
- [ ] Optional: EXPLAIN when fills/orders grow past empty

Issue **stays open** until A/B authenticated measurements are attached (or explicitly waived with owner sign-off).
