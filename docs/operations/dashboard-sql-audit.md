# Dashboard Performance Audit Protocol (P2.5 / Issue #101)

**Status:** Layers A–D measured (2026-07-16; Layer A/B hardened in **#124**). Layer A uses exact success headings + rejects `unavailable` / `dashboard-error-panel`. Warm/soft usable **p95** (n=5): max **877 ms** (Status soft_nav); cold usable remains **single-sample** (`p95 NOT_MEASURED`, n=1). All **77** observed Layer A samples were **under 1.5 s** (max 877 ms) — that is an observation check, not a cold-p95 proof. Layer B warm TTFB p95 **~103–122 ms**; cold TTFB p95 **recorded separately** (n=2). Issue **#121** residual CONFIRMED. H2 (~50 ms engine) = `FOLLOW_UP_REQUIRED`. Indexes `NO_ACTION`. Pack: [`dashboard-railway-performance-evidence.md`](dashboard-railway-performance-evidence.md).

**PR lineage:** Checklist #117; harnesses #119; duplicate #110 closed. This document
is the continuation of Issue #101 (not a new issue).

**Non-goals for this audit delivery**

- No Alembic index migration
- No Cache-TTL changes (evaluate #99 only after measurements)
- No Railway resource scaling
- No strategy, trading, risk, HIP-3, or multi-asset changes

**Core principle:** A fast API is not automatically a fast dashboard.

```text
Navigation
→ Skeleton
→ Next.js TTFB
→ SSR
→ FastAPI
→ PostgreSQL
→ Response size
→ Real data visible
```

Measurement status vocabulary:

| Status | Meaning |
|--------|---------|
| `NOT_MEASURED` | Tooling exists; no trustworthy sample recorded yet |
| `MEASURED` | Real sample attached (JSON artifact or table cell) |
| `OPTIMIZATION_CANDIDATE` | Suspicion + partial evidence; needs before/after |
| `NO_ACTION` | Measured; no change justified |
| `FOLLOW_UP_REQUIRED` | Separate issue only after evidence package complete |

---

## 1. Scope

Audit perceived dashboard load time across:

- Browser navigation and visible/usable content (ROADMAP **1.5 s** target)
- Next.js SSR / TTFB / HTML size
- FastAPI `total_ms`, `db_ms`, `query_count`, `response_bytes`
- PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` for first + cursor pages

Routes (pages):

| Dashboard page | Primary API dependency |
|----------------|------------------------|
| Overview | `/api/v1/dashboard-summary` |
| Status | `/api/v1/status`, `/api/v1/market-data` |
| Positions | `/api/v1/positions` |
| Orders | `/api/v1/orders` |
| Fills | `/api/v1/fills` |
| Equity | `/api/v1/equity` |
| Incidents | `/api/v1/events` |

API routes to instrument/measure:

`/api/v1/status`, `/dashboard-summary`, `/wallet`, `/positions`, `/orders`,
`/fills`, `/equity`, `/events`, `/scheduler-runs`.

Code map:

- `services/paper_trading/readonly_api.py`
- `services/paper_trading/repository.py` (`list_*`, `get_*`)
- `services/paper_trading/perf_observability.py` (Layer C headers + engine listeners)
- `src/app/dashboard/**`, `src/lib/paper-api/client.ts`

---

## 2. Architektur und Messpunkte

```text
Browser ──HTTPS──> paper-trading-dashboard (public)
                         │ SSR fetch
                         └──PRIVATE_PAPER_API_URL──> paper-trading-api (*.railway.internal)
                                                         └──PostgreSQL (private)
```

| Layer | Messpunkt | Tool |
|-------|-----------|------|
| A | Navigation → skeleton → heading / usable content, LCP | `tests/e2e/dashboard-layer-a-perf.spec.ts` |
| B | Next.js TTFB, HTML bytes, warm/cold HTML | `scripts/measure_dashboard_ssr.py` |
| C | FastAPI total/db/query_count/bytes + correlation id | `scripts/measure_dashboard_layer_c_api.py` |
| D | EXPLAIN ANALYZE BUFFERS first + cursor page | `scripts/audit_dashboard_sql_explain.py` |

Distinguish delay sources explicitly:

```text
Browser → Next.js
Next.js SSR
Next.js → FastAPI
FastAPI → PostgreSQL
Rendering im Browser
```

---

## 3. Testumgebung

Record for every measurement run:

| Field | Value |
|-------|-------|
| Date | **2026-07-15** (Railway C/D + login B) |
| Git SHA | `32a94384504fd35ee19ac077799a5c135b4b4aaf` (main after #119) |
| Environment | Railway production (`graceful-compassion`) |
| Region | Dashboard + Postgres **EU West**; API **sfo** |
| API resources | `paper-trading-api` (sfo) |
| Dashboard resources | `paper-trading-dashboard` (EU West) |
| Dataset note | events 437 / scheduler 310 / equity 4 / fills·orders·positions **0** |
| Network path | public `https://bot.save-money.xyz`; Layer C via SSH dashboard → private API |

Artifacts (written by harnesses; do not invent values):

| Artifact | Layer |
|----------|-------|
| `docs/operations/dashboard-layer-a-browser.json` | A (still pending) |
| `docs/operations/dashboard-layer-b-ssr-railway-login-partial.json` | B partial (public `/login`) |
| `docs/operations/dashboard-layer-c-api-railway.json` | C Railway |
| `docs/operations/dashboard-layer-d-explain-railway.json` | D Railway |
| `docs/operations/dashboard-layer-d-explain.json` | D local empty |
| `docs/operations/dashboard-railway-performance-evidence.md` | Summary pack |

---

## 4. Railway-Netzwerkpfad

Important constraints:

- `*.railway.internal` is reachable **only** inside the same Railway project and environment.
- A laptop **cannot** call the private API DNS directly.
- Browser and Next.js measurements use the **public** dashboard URL (`bot.save-money.xyz` or configured domain).
- API-internal and DB measurements must use a Railway-side path that mirrors Next.js → FastAPI:
  - one-off probe service in the same environment, or
  - temporary measurement job, or
  - `railway ssh` into dashboard/api (whichever preserves the private hop under test).
- Do **not** make the private API public only to simplify measurement.
- Always record region + service resources in the report.

---

## 5. Browser- und sichtbarer-Content-Messung

Roadmap budget: **visible/usable content p95 < 1.5 s** — not API-only latency.

### Procedure

```bash
export PAPER_DASHBOARD_BASE_URL=https://bot.save-money.xyz
export PAPER_DASHBOARD_USER=...
export PAPER_DASHBOARD_PASSWORD=...
# Optional: LAYER_A_WARM_REPEATS=5 (default), LAYER_A_COLD_REPEATS=1 (default)
npm run test:dashboard-perf -- tests/e2e/dashboard-layer-a-perf.spec.ts
```

Captures per route (cold hard navigation, warm hard navigation, soft nav):

- Time to **exact success heading** (not ErrorPanel titles like `Positions unavailable`)
- Asserts `dashboard-error-panel` absent and no `/unavailable/i` heading
- Optional `data-testid="dashboard-page-ready"` when deployed UI includes it
- Time to skeleton (`data-testid="dashboard-skeleton"`), if shown
- Skeleton → real data (success heading)
- LCP via `PerformanceObserver` (hard navigation only; soft_nav → `null`)

**Cold vs warm:** Cold uses a **fresh authenticated** `browser.newContext()` per
sample (login may already warm shared assets — not a zero-cache claim). Warm
reuses one authenticated context. Overview soft-nav starts from `/dashboard/status`.

**p95 rule:** `usable_content_p95_ms` is only `MEASURED` when **n ≥ 5** for that
route×mode. With default `LAYER_A_COLD_REPEATS=1`, cold **p95 stays `NOT_MEASURED`**.
Warm/soft defaults to n=5 so their p95 can be reported. Never treat a single sample
as roadmap p95.

**Caveat:** `src/app/dashboard/layout.tsx` sets `dynamic = "force-dynamic"`. Hard
navigations often skip the loading UI because the server holds the response until
SSR finishes. Soft navigations are more likely to expose skeletons.

### Results (#124 remeasure, 2026-07-16)

Usable-content **p95** where n≥5; cold column is the **single sample** (p95 N/A):

| Route | Cold (n=1) | Warm p95 (n=5) | Soft p95 (n=5) | Cold p95 | Status |
|-------|-----------:|---------------:|---------------:|----------|--------|
| Overview | 121 | **64** | **124** | `NOT_MEASURED` | samples `MEASURED` |
| Status | 442 | **420** | **877** | `NOT_MEASURED` | samples `MEASURED` |
| Positions | 446 | **62** | **138** | `NOT_MEASURED` | samples `MEASURED` |
| Orders | 436 | **80** | **140** | `NOT_MEASURED` | samples `MEASURED` |
| Fills | 445 | **68** | **140** | `NOT_MEASURED` | samples `MEASURED` |
| Equity | 455 | **73** | **127** | `NOT_MEASURED` | samples `MEASURED` |
| Incidents | 478 | **66** | **140** | `NOT_MEASURED` | samples `MEASURED` |

Source: `dashboard-layer-a-browser.json` (issue **#124**). Observation check: all **77**
samples < 1.5 s (max **877 ms**). Roadmap **p95 < 1.5 s** is supported for warm/soft
modes with n=5; **cold p95 remains `NOT_MEASURED`**. Success marker: exact heading
(+ ready testid when present); error pages rejected.

---

## 6. Next.js-/SSR-Messung

### Procedure

```bash
export PAPER_DASHBOARD_BASE_URL=https://bot.save-money.xyz
export PAPER_DASHBOARD_USER=...
export PAPER_DASHBOARD_PASSWORD=...
python scripts/measure_dashboard_ssr.py --warm-runs 10 \
  --output docs/operations/dashboard-layer-b-ssr.json
```

Measures authenticated HTML:

- TTFB (headers-ready approximation)
- Full HTML download time
- HTML response size
- Cold vs warm repeats

Server-render duration and per-fetch SSR API time are **included** in the HTML
TTFB when pages `await` API clients at the top level (current dashboard pattern).
Separate server-timings headers are not required for the first pass; if Next.js
`Server-Timing` becomes available later, attach it here.

### Results

Authenticated dashboard routes (`dashboard-layer-b-ssr.json`, warm n=10, cold n=2, #124):

| Route | Warm TTFB p95 | Cold TTFB p95 | HTML bytes p50 | Cold status | Status |
|-------|--------------:|--------------:|---------------:|-------------|--------|
| Overview | **114.7 ms** | **104.0 ms** | 12963 | `MEASURED` | `MEASURED` |
| Status | **111.4 ms** | **107.9 ms** | 17052 | `MEASURED` | `MEASURED` |
| Positions | **103.3 ms** | **105.8 ms** | 12459 | `MEASURED` | `MEASURED` |
| Orders | **122.3 ms** | **101.6 ms** | 12438 | `MEASURED` | `MEASURED` |
| Fills | **106.8 ms** | **88.6 ms** | 12431 | `MEASURED` | `MEASURED` |
| Equity | **103.1 ms** | **101.6 ms** | 16610 | `MEASURED` | `MEASURED` |
| Incidents | **120.2 ms** | **81.7 ms** | 26160 | `MEASURED` | `MEASURED` |

Cold samples are stored in the artifact (`cold_ttfb_p95_ms`, `cold_ttfb_samples_ms`); they are
**not** discarded as warmup-only. Note: cold n=2 → p95 ≈ max of the two samples.

Public `/login` only (historical `dashboard-layer-b-ssr-railway-login-partial.json`, warm n=8): TTFB p95 **187.4 ms**, HTML bytes p50 **6222** (`PARTIAL`).

---

## 7. FastAPI-Messung

### Instrumentation review (#96)

- Listeners attach to the SQLAlchemy **Engine**, not the ORM `Session`.
- `attach_engine_query_metrics` / `detach_engine_query_metrics` prevent listener leaks
  (`get_db_session` `finally`).
- Evidence that `query_count` / `db_ms` rise with real queries:
  `tests/paper_trading/test_perf_instrumentation.py`.
- Overhead doc: `docs/operations/api-db-instrumentation-overhead.md`.
- Issue #101 adds response headers for scripts:

| Header | Field |
|--------|-------|
| `X-Correlation-Id` | correlation id |
| `X-Perf-Total-Ms` | middleware wall clock |
| `X-Perf-Db-Ms` | summed cursor time |
| `X-Perf-Query-Count` | cursor executions |
| `X-Perf-Response-Bytes` | body length when available |

A test that only checks the correlation header is **not** sufficient.

### Procedure

```bash
# Local API, or Railway private hop via probe/ssh
export PAPER_API_BASE_URL=http://127.0.0.1:8080
python scripts/measure_dashboard_layer_c_api.py --warm-runs 20 \
  --output docs/operations/dashboard-layer-c-api.json
```

### Results

**Railway production** (2026-07-15 remodeled), private hop dashboard(EU) -> API(sfo),
warm **20** / warmup **3**. Artifact: `dashboard-layer-c-api-railway.json`.
All routes HTTP **200** with finite `X-Perf-*` and retained correlation IDs.
Unattr./hop are **p95 of per-sample deltas** (not p95(a)-p95(b)).
Table below is the **pre-#121** sfo placement snapshot (historical). Post-co-location
Layer C for status/summary/wallet is in `dashboard-layer-c-after-121.json`
(residual p95 ≈ 49–54 ms). Authenticated Layer A/B (#124) are in §§5–6 —
warm/soft usable p95 under 1.5 s; cold p95 `NOT_MEASURED`.

| Route | Client hop p95 | API total p95 | DB p95 | Unattr. p95 | Hop p95 | Queries | Bytes p50 | Hauptursache |
| ----- | -------------: | ------------: | -----: | ----------: | ------: | ------: | --------: | ------------ |
| /api/v1/status | 3052 | **2903** | 701.4 | **2205** | **157** | 4 | 639 | multi-query + residual |
| /api/v1/dashboard-summary | 3269 | **3121** | 984.2 | **2142** | **150** | 6 | 1175 | highest total/db/q |
| /api/v1/wallet | 2559 | 2409 | 279.1 | **2130** | **151** | 1 | 238 | ~2.13 s residual |
| /api/v1/positions | 2562 | 2408 | 280.6 | **2129** | **152** | 1 | 42 | ~2.13 s residual |
| /api/v1/orders | 2565 | 2413 | 280.9 | **2134** | **155** | 1 | 42 | ~2.13 s residual |
| /api/v1/fills | 2560 | 2411 | 282.6 | **2128** | **157** | 1 | 42 | ~2.13 s residual |
| /api/v1/equity | 2562 | 2409 | 280.5 | **2130** | **156** | 1 | 1210 | ~2.13 s residual |
| /api/v1/events | 2701 | 2410 | 280.7 | **2130** | **296** | 1 | **15191** | residual (size != extra API ms) |
| /api/v1/scheduler-runs | 2845 | 2552 | 422.7 | **2132** | **297** | 1 | **17119** | residual + higher db |

Local API-only samples from Issue #95 remain in
`dashboard-performance-baseline.md` / `.json` and must not be relabeled as
dashboard UX proof.

---

## 8. PostgreSQL-Messung

### Procedure

```bash
export PAPER_TRADING_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test
export PYTHONPATH=services
python scripts/audit_dashboard_sql_explain.py \
  --output docs/operations/dashboard-layer-d-explain.json
```

Session protections (first statements of each route transaction):

- `SET TRANSACTION READ ONLY`
- `SET LOCAL statement_timeout = '30000ms'`

Row counts: `pg_class.reltuples` estimate **before** EXPLAIN; exact `COUNT(*)`
only **after** EXPLAIN (avoids buffer warm-up bias).

For each history route capture first page **and** cursor follow-up page:

- Execution Time, Planning Time
- actual vs estimated rows
- rows examined vs returned (plan text)
- Shared Hit / Read blocks
- Sort Method / Sort Space Used
- Seq Scan vs Index Scan
- Rows Removed by Filter
- LIMIT behavior

### Index gate (replaces “Seq Scan + 10k rows”)

> A Seq Scan is **not automatically bad**, even above 10,000 rows.
>
> Propose or implement an index **only if** scan, sort, or filter demonstrably
> accounts for a material share of the **route** latency **and** a before/after
> comparison on the same representative dataset shows a real benefit.

For every index recommendation document:

1. Source query
2. Existing indexes
3. Baseline plan
4. Baseline execution time + buffers
5. Candidate index tested
6. New plan
7. Time/buffer delta
8. First-page impact
9. Cursor-page impact
10. Expected write overhead
11. Decision: adopt or reject

Audit vs migration are **separate deliveries**. No Alembic migration in #101.

### Results

**Local empty DB** (`paper_trading_test`, 2026-07-15, artifact
`dashboard-layer-d-explain.json`): first pages `MEASURED` at **0 rows**.
Cursor pages `NOT_MEASURED` (empty). **Not** evidence for index decisions —
representative volumes remain `FOLLOW_UP_REQUIRED` on Railway / soak-seeded data.

| Route | Seite | Rows gesamt | Rows zurück | Plan | Exec ms | Buffers | Sort | Empfehlung |
| ----- | ----- | ----------: | ----------: | ---- | ------: | ------- | ---- | ---------- |
| /fills | first | 0 | 0 | Limit (+ sort) | 0.181 | hit=6 | quicksort | `NO_ACTION` on empty set |
| /fills | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /orders | first | 0 | 0 | Limit (+ sort) | 0.011 | hit=4 | quicksort | `NO_ACTION` on empty set |
| /orders | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /equity | first | 0 | 0 | Limit (+ sort) | 0.007 | hit=3 | quicksort | `NO_ACTION` on empty set |
| /equity | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /events | first | 0 | 0 | Limit (+ sort) | 0.024 | hit=4 | quicksort | `NO_ACTION` on empty set |
| /events | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /scheduler-runs | first | 0 | 0 | Limit (+ sort) | 0.011 | hit=6 | quicksort | `NO_ACTION` on empty set |
| /scheduler-runs | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /positions | first | 0 | 0 | Limit (+ sort) | 0.010 | hit=3 | quicksort | `NO_ACTION` on empty set |
| /positions | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |

**Railway production** (2026-07-15), EXPLAIN via SSH `paper-trading-api` → Postgres(EU).
Artifact: `dashboard-layer-d-explain-railway.json`.

| Route | Seite | Rows gesamt | Rows zurück | Plan | Exec ms | Buffers | Sort | Empfehlung |
| ----- | ----- | ----------: | ----------: | ---- | ------: | ------- | ---- | ---------- |
| /fills | first | 0 | 0 | Limit+Sort+Seq | 0.043 | — | — | `NO_ACTION` |
| /fills | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /orders | first | 0 | 0 | Limit+Sort+Seq | 0.031 | — | — | `NO_ACTION` |
| /orders | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /positions | first | 0 | 0 | Limit+Sort+Seq | 0.027 | — | — | `NO_ACTION` |
| /positions | cursor | 0 | — | — | — | — | — | `NOT_MEASURED` (empty) |
| /equity | first | 4 | 4 | Limit+Sort | 0.042 | hit=1 | — | `NO_ACTION` |
| /equity | cursor | 4 | — | — | — | — | — | `NOT_MEASURED` (<limit) |
| /events | first | **437** | 50 | Limit+Sort | 0.074 | hit=7 | quicksort | `NO_ACTION` (≪ route latency) |
| /events | cursor | 437 | 50 | Limit+Sort | 0.087 | hit=7 | quicksort | `NO_ACTION` |
| /scheduler-runs | first | **310** | 50 | Limit+Sort top-N | 0.124 | hit=7 | — | `NO_ACTION` |
| /scheduler-runs | cursor | 310 | 50 | Limit+Sort | 0.186 | hit=7 | — | `NO_ACTION` |

SQL exec is sub-ms; **not** the 2.4–3.3 s API wall clock. Per-route `recommendation_status` is **`NO_ACTION`** (max first/cursor exec vs Layer C route total; 5% share gate).

---

## 9. vorhandene Tabellen und Indizes

Documented from `services/paper_trading/db/orm.py` + migration `003_indexes`.

### Fills (`paper_fills`)

| Existing | Assessment |
|----------|------------|
| `(symbol, fill_time)` | Helps symbol-filtered time lookup; **limited** help for global `ORDER BY fill_time, fill_id` |
| Candidate | `(fill_time, fill_id)` — only after measured before/after |

### Orders (`paper_orders`)

| Existing | Assessment |
|----------|------------|
| `(status, expected_fill_time)` | Worker/status path oriented |
| `(symbol)` | Symbol lookup |
| Gap | No direct index for `(created_at, paper_order_id)` dashboard keyset |

### Equity (`portfolio_snapshots`)

| Existing | Assessment |
|----------|------------|
| `(evaluation_time)` | Partially matching |
| Candidate | `(evaluation_time, snapshot_id)` may add little — **must measure** |

### Events (`audit_events`)

| Existing | Assessment |
|----------|------------|
| `(created_at)` | Partially matching |
| Also | aggregate, cycle, event_type indexes |
| Candidate | add `event_id` to created_at composite only with measurable gain |

### PostgreSQL sort direction

DB-Tree indexes on PostgreSQL can be scanned **backward**. Explicit `DESC` in the
index definition is therefore not mandatory for `ORDER BY ts DESC, id DESC`.
**Column order matching the keyset** matters more.

Optional experiment (no rewrite without gain):

```sql
-- OR form (current repository style)
timestamp < :timestamp
OR (timestamp = :timestamp AND id < :id)

-- tuple form
(timestamp, id) < (:timestamp, :id)
```

---

## 10. Route-für-Route-Ergebnisse

Composite roll-up (#124 Layer A/B + Layer C after-#121 where re-probed).
Browser column = warm usable **p95** (n=5). Soft p95 noted in Ursache.

| Route | Browser warm p95 | TTFB warm p95 | Soft usable p95 | API total p95 | DB p95 | Queries | Bytes | Hauptursache |
| ----- | ---------------: | ------------: | --------------: | ------------: | -----: | ------: | ----: | ------------ |
| Overview | **64 ms** | **115 ms** | **124 ms** | **71 ms** | 15.7 | 6 | 1174 | warm/soft p95 under 1.5 s; heaviest multi-query API |
| Status | **420 ms** | **111 ms** | **877 ms** | **66 ms** | 14.2 | 4 | 638 | soft p95 highest observed; still under 1.5 s |
| Positions | **62 ms** | **103 ms** | **138 ms** | wallet-class ~54 ms (#121) | ~5 | 1 | 42 | thin API not re-probed post-#121 |
| Orders | **80 ms** | **122 ms** | **140 ms** | wallet-class ~54 ms (#121) | ~5 | 1 | 42 | thin API not re-probed post-#121 |
| Fills | **68 ms** | **107 ms** | **140 ms** | wallet-class ~54 ms (#121) | ~5 | 1 | 42 | thin API not re-probed post-#121 |
| Equity | **73 ms** | **103 ms** | **127 ms** | not re-probed post-#121 | — | — | 16610 HTML | warm/soft p95 under 1.5 s |
| Incidents | **66 ms** | **120 ms** | **140 ms** | not re-probed post-#121 | — | — | 26160 HTML | payload size ≠ UX bottleneck |

Cold Layer A p95 remains `NOT_MEASURED` (n=1). API totals for Overview/Status from `dashboard-layer-c-after-121.json`.

---

## 11. Events-Payload-Analyse

### Code facts (no measurement required)

Incidents page (`src/app/dashboard/incidents/page.tsx`) displays only:

- `event_type`
- `aggregate_type`
- `created_at`

It filters client-side with `/FAIL|ERROR|KILL|REJECT|ORPHAN/i`, then falls back
to the first 20 events. The API (`GET /api/v1/events?limit=50`) returns full
sanitized `payload_json` for every item.

### Questions the audit must answer with numbers

1. `response_bytes` with current payload?
2. Share attributable to `payload_json`?
3. Is payload needed on Incidents? (**UI uses no payload fields today**)
4. Lightweight event projection useful?
5. Server-side incident filter useful?
6. Full payload only via detail endpoint?
7. Deltas for API time, serialization, response size, SSR time, browser paint?

`scripts/measure_dashboard_layer_c_api.py` computes payload share when `/events`
is reachable.

| Metric | Value | Status |
|--------|------:|--------|
| response_bytes p50 | **15191** | `MEASURED` (Railway Layer C) |
| payload_json bytes p50 | ~2613 (share x bytes) | `MEASURED` |
| payload_json share p50 | **0.172** | `MEASURED` |
| Incidents uses payload? | No (code review) | `MEASURED` (static) |

### Recommendation status

| Idea | Status | Notes |
|------|--------|-------|
| Lightweight list projection (drop/omit payload on list) | `OPTIMIZATION_CANDIDATE` | Do **not** implement in #101; measure first, then optional follow-up issue |
| Server-side incident type filter | `OPTIMIZATION_CANDIDATE` | Same |
| Detail endpoint for full payload | `OPTIMIZATION_CANDIDATE` | Same |
| Change TTL for `/events` | deferred | Re-evaluate #99 only after audit numbers |

---

## 12. Top-3-Bottlenecks

Prioritize with a scored blend of:

- Visible user latency (Layer A)
- API p95 (Layer C)
- DB share (Layer C `db_ms` / Layer D exec)
- Query count
- Response size
- Call frequency (overview/status > rare history drills)
- Table growth potential

**Current Top-3 (Layers A–D; #121 CONFIRMED; warm/soft Layer A p95 under 1.5 s):**

```text
1. WAS ~2.13 s FastAPI residual — CONFIRMED as API region sfo vs EU Postgres/Dashboard
   (#121): after API → europe-west4 residual p95 ≈ 49–54 ms (see dashboard-fastapi-residual-121.md)
2. Remaining ~50 ms residual + per-request engine/dispose — FOLLOW_UP_REQUIRED (H2; separate issue)
3. GET /api/v1/dashboard-summary — still heaviest multi-query API route after co-location
   (Layer A warm/soft usable p95 still << 1.5 s; cold p95 NOT_MEASURED n=1)
```

Large history JSON (`/events`, `/scheduler-runs`) is **`OPTIMIZATION_CANDIDATE` only**:
API totals match thin routes despite 15–17 KB bodies. Not a data-backed Top-3 item.
Hypothesis “Incidents slow mainly due to payload_json” is **not supported** by Layer C;
Layer A Incidents soft usable p95 **140 ms**. Warm/soft Layer A p95 supports the 1.5 s
roadmap target; cold p95 is still `NOT_MEASURED` until `LAYER_A_COLD_REPEATS≥5`.

---

## 13. geprüfte Optimierungskandidaten

| Candidate | Evidence required | Status |
|-----------|-------------------|--------|
| `(fill_time, fill_id)` on `paper_fills` | before/after EXPLAIN + route p95 | `NO_ACTION` (empty + sub-ms; JSON status aligned) |
| `(created_at, paper_order_id)` on `paper_orders` | before/after | `NO_ACTION` (empty + sub-ms) |
| `(evaluation_time, snapshot_id)` on snapshots | before/after; may be low value | `NO_ACTION` (4 rows + sub-ms) |
| `(created_at, event_id)` on `audit_events` | before/after | `NO_ACTION` (exec << route) |
| Explain / remove ~2.13 s FastAPI residual (region) | Layer C before/after (#121) | `CONFIRMED` — API → EU West |
| Events list projection (no payload) | Layer A/B or parse/projection A/B | `OPTIMIZATION_CANDIDATE` (not Top-3) |
| Cache TTL tweaks (#99) | after audit + staleness review | deferred |
| Tuple keyset rewrite | EXPLAIN + latency delta | `NO_ACTION` until measured benefit |

---

## 14. bestätigte Empfehlungen

| Recommendation | Status |
|----------------|--------|
| Keep audit and index migrations as separate issues/PRs | `MEASURED` (process) |
| Keep CI perf soft-gated until variance known (#102) | confirmed |
| Continue using engine-level query listeners with detach | confirmed (#96 tests) |
| Treat API p95 ≠ dashboard UX | confirmed (this protocol) |
| Compute unattributed residual as p95(per-sample total−db), not p95(total)−p95(db) | confirmed (Layer C probe) |

No index adoption confirmed — Railway Layer D shows sub-ms SQL relative to measured
route latency; indexes are not the bottleneck. Issue **#121** confirmed the former
~2.13 s residual as API region mismatch (now co-located). Remaining ~50 ms residual /
per-request engine disposal is `FOLLOW_UP_REQUIRED` — not an Alembic migration.

---

## 15. verworfene Empfehlungen

| Recommendation | Why discarded |
|----------------|---------------|
| “Add index whenever Seq Scan + ≥10k rows” | Replaced by latency-share + before/after gate |
| Publicize private Railway API for easier probing | Security / architecture violation |
| Ship index migration inside #101 | Scope split: audit vs migration |
| Change cache TTLs during audit | #99 post-audit only |
| Invent p50/p95 placeholders as “results” | Forbidden |
| Rank “cross-region dominates” as proven Top-1 **without** before/after | Forbidden during #101; later **CONFIRMED** in #121 with before/after |
| Rank history JSON as Top-3 from size alone | Layer C: large bodies with flat API totals vs thin routes |

---

## 16. offene Messungen

| Item | Status |
|------|--------|
| Layer A Playwright against Railway public URL | `MEASURED` (`dashboard-layer-a-browser.json`) |
| Layer B authenticated SSR TTFB | `MEASURED` (`dashboard-layer-b-ssr.json`) |
| Layer B public `/login` SSR | `PARTIAL` (historical) |
| Layer C via Railway **private** API hop | `MEASURED` (warm 20/3; HTTP-validated; #121 after for 3 routes) |
| Layer D EXPLAIN on empty local `paper_trading_test` | `MEASURED` (first page only) |
| Layer D EXPLAIN on Railway (+ cursor where rows allow) | `MEASURED` |
| Top-3 from Layer A–D data | `MEASURED` (UX within 1.5 s after #121) |
| Events payload byte share on Railway | `MEASURED` (~17%) |
| Index before/after packages | not started / not justified (`NO_ACTION`) |
| Co-location before/after for ~2.13 s residual (#121) | `CONFIRMED` / `MEASURED` |
| Remaining ~50 ms residual / process-scoped engine | `FOLLOW_UP_REQUIRED` (out of #101 close scope) |

---

## 17. Vorher-/Nachher-Protokoll

Use one block per candidate:

```text
Candidate:
Route(s):
Dataset (row counts / date / env):
Baseline plan (first + cursor):
Baseline exec ms / buffers:
Baseline API p95 / browser usable p95:
Baseline unattributed residual p95 (per-sample total−db):
Baseline private hop p95 (per-sample client−total):
Change applied (test index / projection / region move) — temporary:
New plan:
New exec ms / buffers:
New residual / hop p95:
Delta:
Write-overhead assessment:
Decision: ADOPT | REJECT
Rollback plan:
Follow-up issue: (only if ADOPT and migration needed)
```

See `dashboard-fastapi-residual-121.md` for the #121 region before/after package. Additional candidate blocks still attach here when run.

---

## Cache recommendations (post-measurement only)

Do **not** change TTLs in this audit. After numbers exist, recommend per data class:

| Class | Options | Constraint |
|-------|---------|------------|
| Readiness / critical warnings | keep **1–2 s** | Post-#121 origin ~50–70 ms API; TTL still for stampede/staleness |
| Wallet / open positions | **3–5 s** remain plausible | Stampede control only |
| Orders / fills tables | **3–5 s** | Tables empty in prod evidence |
| Equity / events / scheduler history | **15–30 s** remains reasonable | Size ≠ proven API latency driver |

Do **not** lengthen TTLs as a substitute for locating residual cost. The #121 region fix removed the ~2.13 s class of delay. Issue #99 final approval still waits on authenticated A/B + optional remaining-~50 ms follow-up.

---

## CI performance gate

Keep soft for now (`tests/perf` reporting / artifacts). Propose a hard gate only when:

- Environment stable
- Enough history exists
- Natural variance known
- Budgets validated

---

## Acceptance checklist for closing Issue #101

- [x] Browser, SSR, API, and DB measurements documented separately
- [x] Navigation → skeleton and → real data measured (Layer A)
- [x] Next.js authenticated TTFB measured (Layer B); public `/login` historical PARTIAL kept
- [x] API exposes/logs `total_ms`, `db_ms`, `query_count`, `response_bytes`
- [x] Railway measurement path documented correctly
- [x] Top-3 chosen from real Layer A–D data (UX within 1.5 s after #121)
- [x] `/events` + `payload_json` analyzed with sizes (~17% share)
- [x] History first + cursor pages have `EXPLAIN` where rows allow (empty tables noted)
- [x] Existing indexes considered
- [x] No index recommended solely because of Seq Scan
- [x] Index candidates: no before/after required — gate not met (`NO_ACTION`)
- [x] Index migrations still separate
- [x] Cache recommendations derived from measurements only (#99 still deferred)
- [x] Honest status labels (A/B MEASURED; empty cursor EXPLAIN still noted)
- [x] Duplicate PR #110 closed; #117 recognized as checklist merge
- [x] Authenticated A/B artifacts attached (`dashboard-layer-a-browser.json`, `dashboard-layer-b-ssr.json`)
