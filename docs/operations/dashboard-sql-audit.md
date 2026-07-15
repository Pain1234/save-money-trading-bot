# Dashboard Performance Audit Protocol (P2.5 / Issue #101)

**Status:** Measurable audit protocol + harnesses. Real Railway end-to-end values
remain `NOT_MEASURED` until executed via the documented network path.
**PR lineage:** Checklist landed in #117; duplicate lane #110 closed. This document
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
| Date | `NOT_MEASURED` (Railway) / fill when run |
| Git SHA | fill when run |
| Environment | local PostgreSQL / Railway production |
| Region | fill for Railway |
| API resources | fill Railway service size |
| Dashboard resources | fill Railway service size |
| Dataset note | row counts per history table (Layer D) |
| Network path | public dashboard URL vs private API probe |

Artifacts (written by harnesses; do not invent values):

| Artifact | Layer |
|----------|-------|
| `docs/operations/dashboard-layer-a-browser.json` | A |
| `docs/operations/dashboard-layer-b-ssr.json` | B |
| `docs/operations/dashboard-layer-c-api.json` | C |
| `docs/operations/dashboard-layer-d-explain.json` | D |

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
npm run test:dashboard-perf -- tests/e2e/dashboard-layer-a-perf.spec.ts
```

Captures per route (cold hard navigation, warm hard navigation, soft nav):

- Time to visible page heading
- Time to skeleton (`data-testid="dashboard-skeleton"`), if shown
- Skeleton → real data (heading/table)
- LCP via `PerformanceObserver` (hard navigation only; soft_nav → `null`)
- Full navigation to usable content

**Cold vs warm:** Cold uses a **fresh authenticated** `browser.newContext()` per
route (login may already warm shared assets — not a zero-cache claim). Warm
reuses one authenticated context. Overview soft-nav starts from `/dashboard/status`.

**Caveat:** `src/app/dashboard/layout.tsx` sets `dynamic = "force-dynamic"`. Hard
navigations often skip the loading UI because the server holds the response until
SSR finishes. Soft navigations are more likely to expose skeletons. On the first
Railway run, verify hard-nav LCP is non-null (observer may miss if read before a
final candidate).

### Results

| Route | Mode | Browser usable p95 | Skeleton | Skeleton→Daten | LCP | Status |
|-------|------|-------------------:|---------:|---------------:|----:|--------|
| Overview | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |
| Status | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |
| Positions | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |
| Orders | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |
| Fills | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |
| Equity | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |
| Incidents | cold/warm/soft | — | — | — | — | `NOT_MEASURED` |

Populate only from `dashboard-layer-a-browser.json`. Never invent timings.

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

| Route | TTFB p95 | HTML total p95 | HTML bytes p50 | Status |
|-------|---------:|---------------:|---------------:|--------|
| Overview | — | — | — | `NOT_MEASURED` |
| Status | — | — | — | `NOT_MEASURED` |
| Positions | — | — | — | `NOT_MEASURED` |
| Orders | — | — | — | `NOT_MEASURED` |
| Fills | — | — | — | `NOT_MEASURED` |
| Equity | — | — | — | `NOT_MEASURED` |
| Incidents | — | — | — | `NOT_MEASURED` |

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

| Route | Browser p95 | TTFB | Skeleton→Daten | API p95 | DB p95 | Queries | Bytes | Hauptursache |
| ----- | ----------: | ---: | -------------: | ------: | -----: | ------: | ----: | ------------ |
| /api/v1/status | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending layers A–D |
| /api/v1/dashboard-summary | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| /api/v1/wallet | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| /api/v1/positions | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| /api/v1/orders | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| /api/v1/fills | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| /api/v1/equity | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| /api/v1/events | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending payload analysis |
| /api/v1/scheduler-runs | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |

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

Railway / production-like EXPLAIN: `NOT_MEASURED` (private DB hop required).

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

Composite roll-up (fill after Layers A–D on the **same** environment):

| Route | Browser p95 | TTFB | Skeleton→Daten | API p95 | DB p95 | Queries | Bytes | Hauptursache |
| ----- | ----------: | ---: | -------------: | ------: | -----: | ------: | ----: | ------------ |
| Overview | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| Status | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| Positions | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| Orders | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| Fills | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| Equity | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |
| Incidents | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | pending |

Empty cells are **not** completed results.

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
| response_bytes p50 | — | `NOT_MEASURED` |
| payload_json bytes p50 | — | `NOT_MEASURED` |
| payload_json share p50 | — | `NOT_MEASURED` |
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

**Current Top-3:** `FOLLOW_UP_REQUIRED` — do not invent ranks without real samples.

Working hypothesis to validate (not a claim):

```text
1. /dashboard/incidents — response size via payload_json (static evidence only)
2. /dashboard/equity — SSR + history response
3. /dashboard/status — multiple runtime reads / large JSON dump in UI
```

Promote to confirmed Top-3 only after Layers A–D on one environment.

---

## 13. geprüfte Optimierungskandidaten

| Candidate | Evidence required | Status |
|-----------|-------------------|--------|
| `(fill_time, fill_id)` on `paper_fills` | before/after EXPLAIN + route p95 | `FOLLOW_UP_REQUIRED` |
| `(created_at, paper_order_id)` on `paper_orders` | before/after | `FOLLOW_UP_REQUIRED` |
| `(evaluation_time, snapshot_id)` on snapshots | before/after; may be low value | `FOLLOW_UP_REQUIRED` |
| `(created_at, event_id)` on `audit_events` | before/after | `FOLLOW_UP_REQUIRED` |
| Events list projection (no payload) | Layer C bytes + Layer A/B | `OPTIMIZATION_CANDIDATE` |
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

No index adoption confirmed yet (await Layer D + route deltas).

---

## 15. verworfene Empfehlungen

| Recommendation | Why discarded |
|----------------|---------------|
| “Add index whenever Seq Scan + ≥10k rows” | Replaced by latency-share + before/after gate |
| Publicize private Railway API for easier probing | Security / architecture violation |
| Ship index migration inside #101 | Scope split: audit vs migration |
| Change cache TTLs during audit | #99 post-audit only |
| Invent p50/p95 placeholders as “results” | Forbidden |

---

## 16. offene Messungen

| Item | Status |
|------|--------|
| Layer A Playwright against Railway public URL | `NOT_MEASURED` |
| Layer B SSR TTFB against public dashboard | `NOT_MEASURED` |
| Layer C via Railway **private** API hop | `NOT_MEASURED` |
| Layer D EXPLAIN on empty local `paper_trading_test` | `MEASURED` (first page only; see artifact) |
| Layer D EXPLAIN on production-like row counts + cursor pages | `NOT_MEASURED` (Railway/private DB hop) |
| Top-3 confirmed from real scored data | `FOLLOW_UP_REQUIRED` |
| Events payload byte share on Railway | `NOT_MEASURED` |
| Index before/after packages | not started |

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
Change applied (test index / projection) — temporary:
New plan:
New exec ms / buffers:
Delta:
Write-overhead assessment:
Decision: ADOPT | REJECT
Rollback plan:
Follow-up issue: (only if ADOPT and migration needed)
```

No rows yet — attach when an experiment is run.

---

## Cache recommendations (post-measurement only)

Do **not** change TTLs in this audit. After numbers exist, recommend per data class:

| Class | Options | Constraint |
|-------|---------|------------|
| Readiness / critical warnings | no cache or 1–2 s | Must not hide degradation |
| Wallet / open positions | 1–2 s or 3–5 s | |
| Orders / fills tables | 3–5 s | |
| Equity / events / scheduler history | 15–30 s | Already 30 s on API today — re-validate |

Issue #99 final approval waits on this audit.

---

## CI performance gate

Keep soft for now (`tests/perf` reporting / artifacts). Propose a hard gate only when:

- Environment stable
- Enough history exists
- Natural variance known
- Budgets validated

---

## Acceptance checklist for closing Issue #101

- [ ] Browser, SSR, API, and DB measurements documented separately
- [ ] Navigation → skeleton and → real data measured
- [ ] Next.js TTFB measured
- [ ] API exposes/logs `total_ms`, `db_ms`, `query_count`, `response_bytes`
- [ ] Railway measurement path documented correctly
- [ ] Top-3 routes chosen from real data
- [ ] `/events` + `payload_json` analyzed with sizes
- [ ] History first + cursor pages have `EXPLAIN (ANALYZE, BUFFERS)`
- [ ] Existing indexes considered
- [ ] No index recommended solely because of Seq Scan
- [ ] Every index candidate has measured before/after benefit
- [ ] Index migrations still separate
- [ ] Cache recommendations derived from measurements only
- [ ] Open Railway steps marked `NOT_MEASURED` honestly
- [ ] Duplicate PR #110 closed; #117 recognized as checklist merge
- [ ] Tests and executed measurements documented in the PR
