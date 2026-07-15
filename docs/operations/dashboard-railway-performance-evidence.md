# Railway dashboard performance evidence (Issue #101)

**Date:** 2026-07-15 (Layer C remodeled: HTTP-validated, warm **20** / warmup **3**, per-sample residual/hop p95)
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

**Architecture note (hypothesis input, not proven root cause):** Dashboard and Postgres are in EU West; the read-only API is in **sfo**. That placement is the **leading hypothesis** for the ~2.13 s unattributed FastAPI residual, but it is **not** confirmed without APM instrumentation or a co-location before/after.

Private API was **not** made public. Layer C used SSH into the dashboard service.

## Artifacts

| Layer | Artifact | Status |
|-------|----------|--------|
| A Browser usable content | — | `NOT_MEASURED` — needs `PAPER_DASHBOARD_USER` / `PAPER_DASHBOARD_PASSWORD` |
| B Next.js SSR (authenticated) | — | `NOT_MEASURED` — same credentials |
| B public `/login` only | [`dashboard-layer-b-ssr-railway-login-partial.json`](dashboard-layer-b-ssr-railway-login-partial.json) | `PARTIAL` |
| C FastAPI private hop | [`dashboard-layer-c-api-railway.json`](dashboard-layer-c-api-railway.json) | `MEASURED` (HTTP 200 + finite `X-Perf-*`; warm 20/3) |
| D PostgreSQL EXPLAIN | [`dashboard-layer-d-explain-railway.json`](dashboard-layer-d-explain-railway.json) | `MEASURED` (`recommendation_status`: **`NO_ACTION`**; relative gate vs Layer C totals) |

Probe helper (dashboard Node): `scripts/railway_layer_c_probe.js`
SSH runner: `scripts/run_railway_layer_c_probe.py`
Requires `res.ok`, finite perf headers, and retains `sample_status_codes` + `sample_correlation_ids`.
Residuals/hops are **p95 of per-sample deltas**, not `p95(a) − p95(b)`.

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
Warm runs: **20** (after **3** discarded warm-ups). All routes `MEASURED`, `sample_status_codes=[200]`, correlation IDs retained.

| Route | Client p95 (ms) | API total p95 (ms) | DB p95 (ms) | Unattr. p95 (per-sample total-db) | Hop p95 (per-sample client-total) | Queries p95 | Bytes p50 | Events payload share |
|-------|----------------:|-------------------:|------------:|----------------------------------:|----------------------------------:|------------:|----------:|---------------------:|
| status | 3052 | 2903 | 701.4 | **2205** | **157** | 4 | 639 | — |
| dashboard_summary | 3269 | 3121 | 984.2 | **2142** | **150** | 6 | 1175 | — |
| wallet | 2559 | 2409 | 279.1 | **2130** | **151** | 1 | 238 | — |
| positions | 2562 | 2408 | 280.6 | **2129** | **152** | 1 | 42 | — |
| orders | 2565 | 2413 | 280.9 | **2134** | **155** | 1 | 42 | — |
| fills | 2560 | 2411 | 282.6 | **2128** | **157** | 1 | 42 | — |
| equity | 2562 | 2409 | 280.5 | **2130** | **156** | 1 | 1210 | — |
| events | 2701 | 2410 | 280.7 | **2130** | **296** | 1 | **15191** | **0.172** |
| scheduler_runs | 2845 | 2552 | 422.7 | **2132** | **297** | 1 | **17119** | — |


Interpretation (measurement-backed only):

- Every monitored API call is **already ~2.4–3.1 s** before browser paint — **above** the ROADMAP 1.5 s usable-content budget on the API hop alone.
- Per-sample **`total_ms − db_ms`** p95 clusters at **~2.13 s** (wallet **2130** ms; status higher at **2205** ms). This residual is **inside** FastAPI wall-clock.
- Per-sample private hop p95 (`client − total`) is **~150–157 ms** on small bodies; **~296–297 ms** on large history bodies. Hop is real but **not** the dominant share.
- `db_ms` is elevated vs local baselines (~280 ms single-query; up to ~984 ms on summary). Attributing that specifically to “API(sfo)→Postgres(EU)” remains a **hypothesis** aligned with region metadata.
- `/events` has **~15 KB** vs 42–238 B on thin routes but **nearly the same API total** as `/wallet`. `/scheduler-runs` extra total ≈ extra `db_ms`. History JSON size is therefore an **`OPTIMIZATION_CANDIDATE`**, not a data-backed Top-3 bottleneck without A/B projection / parse measurements.

---

## Layer D — PostgreSQL EXPLAIN (`MEASURED`)

Host: SSH `paper-trading-api` with `SET TRANSACTION READ ONLY` + `SET LOCAL statement_timeout`.
URL driver normalized to `postgresql+psycopg://`.
Index gate uses max(first, cursor) exec vs Layer C route `total_ms` p95 (5% material share).

| Route | Rows exact | First page | Cursor page | First exec ms | `recommendation_status` |
|-------|-----------:|------------|-------------|--------------:|-------------------------|
| /fills | 0 | MEASURED | NOT_MEASURED (empty) | 0.043 | **`NO_ACTION`** |
| /orders | 0 | MEASURED | NOT_MEASURED (empty) | 0.031 | **`NO_ACTION`** |
| /positions | 0 | MEASURED | NOT_MEASURED (empty) | 0.027 | **`NO_ACTION`** |
| /equity | 4 | MEASURED | NOT_MEASURED (<100 rows) | 0.042 | **`NO_ACTION`** |
| /events | **437** | MEASURED | **MEASURED** | 0.074 / 0.087 | **`NO_ACTION`** |
| /scheduler-runs | **310** | MEASURED | **MEASURED** | 0.124 / 0.186 | **`NO_ACTION`** |

Index conclusion from this environment:

- SQL execution is **sub-millisecond** and ≪ 5% of measured route latency → **`NO_ACTION`**.
- Seq Scan on empty or tiny tables is `NO_ACTION` under the evidence gate.
- History growth (events/scheduler ~300–400 rows) is not the current user-visible bottleneck.

---

## Top-3 bottlenecks (scored from Railway samples only)

1. **~2.13 s unattributed FastAPI residual (p95 of per-sample `total_ms − db_ms`); region split is the leading hypothesis**
   Stable across routes (~2128–2142 ms; status ~2205 ms). Call frequency: every dashboard page. **Not** proven as “cross-region dominates” without instrumentation or co-location before/after.
2. **`GET /api/v1/dashboard-summary`**
   Highest API total / db / query_count (p95 total **3121** ms, db **984** ms, **6** queries) — Overview path.
3. **`GET /api/v1/status`**
   Next multi-query cost (p95 total **2903** ms, db **701** ms, **4** queries).

**Not Top-3 (demoted):** large history JSON (`/events`, `/scheduler-runs`) — response size differs sharply while API totals stay flat vs thin routes. Keep as **`OPTIMIZATION_CANDIDATE`** (projection / list payload) pending A/B or Layer A/B impact.

Hypothesis “Incidents slow mainly due to payload_json” is **not supported** by Layer C: payload share ≈17% and API time matches ~42 B routes.

---

## Cache recommendations (from these values only)

| Data class | Recommendation | Reason |
|------------|----------------|--------|
| Readiness / status / summary | Keep **1–2 s** (or no-store for forced refresh) | Origin already ~2.5–3.1 s; TTL cannot remove the ~2.13 s residual |
| Wallet / positions | **3–5 s** remain plausible | Stampede control only |
| Orders / fills | **3–5 s** | Tables currently empty in prod DB evidence |
| Equity / events / scheduler | **15–30 s** remains reasonable | Size candidate ≠ proven latency driver |

Do **not** treat longer TTLs as a substitute for identifying/removing the unattributed FastAPI residual (hypothesis: co-locate API with Postgres).

---

## Index candidates

| Candidate | Decision |
|-----------|----------|
| All composite history indexes from checklist | **`NO_ACTION`** — max(first,cursor) exec ≪ 5% of route `total_ms` |
| Co-locate / instrument to explain ~2.13 s residual | **`FOLLOW_UP_REQUIRED`** (ops/APM) — not an Alembic change |
| Lightweight `/events` projection | **`OPTIMIZATION_CANDIDATE`** — not Top-3 without UX delta |
| Speculative index migration ticket | **Not opened** — evidence package for indexes not met |

---

## Still open for closing Issue #101

- [ ] Layer A authenticated browser timings (needs dashboard password in env)
- [ ] Layer B authenticated SSR TTFB for Overview/Status/…
- [ ] Confirm hard-nav LCP non-null on Railway once A runs
- [ ] Instrument or co-locate to confirm/reject region hypothesis for the ~2.13 s residual (before/after Layer C)
- [ ] Optional: EXPLAIN when fills/orders grow past empty

Issue **stays open** until A/B authenticated measurements are attached (or explicitly waived with owner sign-off).
