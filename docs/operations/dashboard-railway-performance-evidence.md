# Railway dashboard performance evidence (Issue #101)

> **Update (Issue #121, 2026-07-15):** Region hypothesis **CONFIRMED**. After moving paper-trading-api sfo → europe-west4-drams3a with no other changes, residual p95 fell from ~2155–2176 ms to ~49–54 ms on wallet/summary/status. See dashboard-fastapi-residual-121.md and dashboard-layer-c-before-121.json / dashboard-layer-c-after-121.json.

> **Update (authenticated A/B, 2026-07-16):** Layer A + Layer B measured against `https://bot.save-money.xyz`. Artifacts: `dashboard-layer-a-browser.json`, `dashboard-layer-b-ssr.json`. Usable content max **869 ms** (Status soft_nav); hard-nav LCP non-null; warm SSR TTFB p95 **~106–135 ms**. Roadmap **1.5 s** usable-content budget **met**. Indexes remain `NO_ACTION`. H2 (~50 ms residual / per-request engine) stays `FOLLOW_UP_REQUIRED` outside #101 close scope.

**Date:** 2026-07-15 (Layer C) / 2026-07-16 (Layers A/B)
**Project:** `graceful-compassion` / environment `production`
**Deployed Git SHA (main after #122):** `d8d0c402861411d2e9f9044529ffe106d5f4ed5c`
**Method:** Harnesses from PR #119 via `railway ssh` (private hop) + public URL authenticated probes

## Environment (measured)

| Service | Region | Role in measurement |
|---------|--------|---------------------|
| `paper-trading-dashboard` | **EU West** (`europe-west4-drams3a`) | Public HTTPS `https://bot.save-money.xyz`; Layer A/B origin; Layer C probe origin |
| `paper-trading-api` | **EU West** (`europe-west4-drams3a`) after #121 | Private `paper-trading-api.railway.internal:8080`; was **sfo** in the pre-#121 Layer C table |
| `paper-trading-postgres` | **EU West** (`europe-west4-drams3a`) | `postgres.railway.internal` |
| `paper-trading-worker` | EU West | Not exercised |

**Architecture (post-#121):** Dashboard, API, and Postgres are co-located in EU West. The former ~2.13 s FastAPI residual is explained by the prior API `sfo` placement (**CONFIRMED** via one-factor before/after).

Private API was **not** made public. Layer C used SSH into the dashboard service.

## Artifacts

| Layer | Artifact | Status |
|-------|----------|--------|
| A Browser usable content | [`dashboard-layer-a-browser.json`](dashboard-layer-a-browser.json) | `MEASURED` |
| B Next.js SSR (authenticated) | [`dashboard-layer-b-ssr.json`](dashboard-layer-b-ssr.json) | `MEASURED` |
| B public `/login` only | [`dashboard-layer-b-ssr-railway-login-partial.json`](dashboard-layer-b-ssr-railway-login-partial.json) | `PARTIAL` (historical) |
| C FastAPI private hop (pre-#121) | [`dashboard-layer-c-api-railway.json`](dashboard-layer-c-api-railway.json) | `MEASURED` (historical sfo API) |
| C FastAPI before/after #121 | [`dashboard-layer-c-before-121.json`](dashboard-layer-c-before-121.json) / [`dashboard-layer-c-after-121.json`](dashboard-layer-c-after-121.json) | `MEASURED` |
| D PostgreSQL EXPLAIN | [`dashboard-layer-d-explain-railway.json`](dashboard-layer-d-explain-railway.json) | `MEASURED` (`recommendation_status`: **`NO_ACTION`**) |

Probe helper (dashboard Node): `scripts/railway_layer_c_probe.js`
SSH runner: `scripts/run_railway_layer_c_probe.py`
Requires `res.ok`, finite perf headers, and retains `sample_status_codes` + `sample_correlation_ids`.
Residuals/hops are **p95 of per-sample deltas**, not `p95(a) − p95(b)`.

---

## Layer A — browser usable content (`MEASURED`)

Authenticated Playwright (`npm run test:dashboard-perf -- tests/e2e/dashboard-layer-a-perf.spec.ts`), 2026-07-16.

| Metric | Value |
|--------|------:|
| Routes × modes | 7 × (cold/warm/soft) = 21 samples |
| Hard-nav LCP | non-null on all routes |
| Worst usable content | **869 ms** (Status soft_nav) |
| Typical warm hard-nav usable | **47–61 ms** (most pages); Status warm **372 ms** |
| 1.5 s budget | **met** on all samples |

Skeletons usually absent on hard navigation (`force-dynamic`); soft_nav more often shows skeleton. Details in `dashboard-sql-audit.md` §5.

---

## Layer B — authenticated SSR (`MEASURED`)

`python scripts/measure_dashboard_ssr.py --warm-runs 10`, 2026-07-16.

| Route | TTFB p95 (ms) | HTML total p95 (ms) | HTML bytes p50 |
|-------|--------------:|--------------------:|---------------:|
| Overview | 106.2 | 113.9 | 12963 |
| Status | 108.8 | 144.2 | 17052 |
| Positions | 116.5 | 122.3 | 12459 |
| Orders | 116.2 | 124.3 | 12438 |
| Fills | 112.7 | 121.7 | 12431 |
| Equity | 118.1 | 139.3 | 16610 |
| Incidents | 134.6 | 160.1 | 26160 |

Historical public `/login` only: TTFB p95 **187.4 ms**, HTML bytes p50 **6222**.

---

## Layer C — FastAPI via private Next.js→API hop (`MEASURED`)

### Pre-#121 (API in sfo) — historical snapshot

Probe service: `paper-trading-dashboard` → `http://paper-trading-api.railway.internal:8080`
Warm runs: **20** (after **3** discarded warm-ups). Artifact: `dashboard-layer-c-api-railway.json`.

| Route | Client p95 (ms) | API total p95 (ms) | DB p95 (ms) | Unattr. p95 (per-sample total-db) | Hop p95 | Queries p95 | Bytes p50 |
|-------|----------------:|-------------------:|------------:|----------------------------------:|--------:|------------:|----------:|
| status | 3052 | 2903 | 701.4 | **2205** | **157** | 4 | 639 |
| dashboard_summary | 3269 | 3121 | 984.2 | **2142** | **150** | 6 | 1175 |
| wallet | 2559 | 2409 | 279.1 | **2130** | **151** | 1 | 238 |
| positions | 2562 | 2408 | 280.6 | **2129** | **152** | 1 | 42 |
| orders | 2565 | 2413 | 280.9 | **2134** | **155** | 1 | 42 |
| fills | 2560 | 2411 | 282.6 | **2128** | **157** | 1 | 42 |
| equity | 2562 | 2409 | 280.5 | **2130** | **156** | 1 | 1210 |
| events | 2701 | 2410 | 280.7 | **2130** | **296** | 1 | **15191** |
| scheduler_runs | 2845 | 2552 | 422.7 | **2132** | **297** | 1 | **17119** |

Interpretation (pre-#121): API hop alone exceeded the 1.5 s UX budget; ~2.13 s unattributed residual dominated.

### Post-#121 (API co-located EU West) — confirmatory probe

Routes status / dashboard_summary / wallet only (`dashboard-layer-c-after-121.json`):

| Route | API total p95 (ms) | DB p95 (ms) | Residual p95 (ms) | Queries |
|-------|-------------------:|------------:|------------------:|--------:|
| status | 66 | 14.2 | ~52 | 4 |
| dashboard_summary | 71.2 | 15.7 | ~54 | 6 |
| wallet | 53.7 | 5.1 | ~49 | 1 |

---

## Layer D — PostgreSQL EXPLAIN (`MEASURED`, `NO_ACTION`)

See `dashboard-layer-d-explain-railway.json`. Composite indexes not justified: exec ≪ route totals. Empty tables → cursor pages remain `NOT_MEASURED (empty)`.

---

## Index candidates

| Candidate | Decision |
|-----------|----------|
| All composite history indexes from checklist | **`NO_ACTION`** — max(first,cursor) exec ≪ 5% of route `total_ms`; Layer A UX already under budget |
| Co-locate / instrument ~2.13 s residual | **`CONFIRMED`** via #121 (API → EU West) |
| Remaining ~50 ms + per-request engine | **`FOLLOW_UP_REQUIRED`** (H2) — not Alembic; not #101 close blocker |
| Lightweight `/events` projection | **`OPTIMIZATION_CANDIDATE`** — Incidents Layer A usable ≤124 ms |
| Speculative index migration ticket | **Not opened** — evidence package for indexes not met |

---

## Closing Issue #101

- [x] Layer A authenticated browser timings attached
- [x] Layer B authenticated SSR TTFB attached
- [x] Hard-nav LCP non-null on Railway confirmed
- [x] Region hypothesis for ~2.13 s residual confirmed (#121)
- [ ] Optional later: EXPLAIN when fills/orders grow past empty (not a close blocker)
- [ ] Optional later: H2 process-scoped engine follow-up (separate issue)

Issue **#101** is closable with this evidence pack + audit checklist.
