# Railway dashboard performance evidence (Issue #101)

> **Update (Issue #124 cold p95, 2026-07-16):** `LAYER_A_COLD_REPEATS=5` (+ 7s login gap). Cold usable p95 now `MEASURED` on all seven routes (max cold p95 **443 ms** Incidents; max overall soft **871 ms** Status). All 105 samples under 1.5 s.

> **Update (Issue #124, 2026-07-16):** Layer A/B measurement honesty hardened. Exact success headings + `dashboard-error-panel` / `dashboard-page-ready` markers; warm/soft usable p95 with n=5; Layer B cold TTFB recorded separately.

> **Update (Issue #121, 2026-07-15):** Region hypothesis **CONFIRMED**. After moving paper-trading-api sfo → europe-west4-drams3a with no other changes, residual p95 fell from ~2155–2176 ms to ~49–54 ms on wallet/summary/status. See dashboard-fastapi-residual-121.md and dashboard-layer-c-before-121.json / dashboard-layer-c-after-121.json.

> **Update (authenticated A/B close #101, 2026-07-16):** Initial A/B artifacts attached via PR #123. Superseded for honesty by #124 remeasure (markers + p95 rules + cold Layer B).

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

## Layer A — browser usable content (`MEASURED` p95 cold/warm/soft)

Authenticated Playwright (`LAYER_A_WARM_REPEATS=5`, `LAYER_A_COLD_REPEATS=5`, gap 7000 ms).

| Metric | Value |
|--------|------:|
| Samples | 105 (7 routes × 5 cold/warm/soft) |
| Success criterion | Exact success heading; no `/unavailable/` heading; no `dashboard-error-panel` |
| Observed max usable | **871 ms** (Status soft_nav) |
| All samples under 1.5 s | **yes** |
| Cold/warm/soft usable p95 | **all `MEASURED`** (n=5); max soft p95 **871 ms**; max cold p95 **443 ms** |

| Route | Cold p95 | Warm p95 | Soft p95 |
|-------|---------:|---------:|---------:|
| Overview | 91 | 70 | 141 |
| Status | 395 | 389 | 871 |
| Positions | 375 | 67 | 140 |
| Orders | 390 | 64 | 145 |
| Fills | 370 | 75 | 138 |
| Equity | 96 | 62 | 135 |
| Incidents | 443 | 72 | 139 |

Details in `dashboard-sql-audit.md` §5.

---

## Layer B — authenticated SSR (`MEASURED`, cold + warm)

`python scripts/measure_dashboard_ssr.py --warm-runs 10 --cold-runs 2`, issue **#124**.

| Route | Warm TTFB p95 (ms) | Cold TTFB p95 (ms) | HTML bytes p50 |
|-------|-------------------:|-------------------:|---------------:|
| Overview | 114.7 | 104.0 | 12963 |
| Status | 111.4 | 107.9 | 17052 |
| Positions | 103.3 | 105.8 | 12459 |
| Orders | 122.3 | 101.6 | 12438 |
| Fills | 106.8 | 88.6 | 12431 |
| Equity | 103.1 | 101.6 | 16610 |
| Incidents | 120.2 | 81.7 | 26160 |

Cold samples are retained in the JSON (`cold_ttfb_samples_ms`); not discarded as warmup-only.
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

## Closing Issue #101 / follow-up #124

- [x] Layer A authenticated browser timings attached (exact success markers in #124)
- [x] Layer B authenticated SSR TTFB attached (cold + warm in #124)
- [x] Cold/warm/soft usable p95 under 1.5 s (n=5 each)
- [x] Region hypothesis for ~2.13 s residual confirmed (#121)
- [ ] Optional later: EXPLAIN when fills/orders grow past empty
- [ ] Optional later: H2 process-scoped engine follow-up (separate issue)

Issue **#101** closed via PR #123; honesty + cold p95 tracked in **#124** / follow-up PRs.
