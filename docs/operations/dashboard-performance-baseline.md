# Dashboard and API performance baseline (P2.5 / Issue #95)

**Status:** Procedure + local main measurement. Prior “−41% overview” claims based on
`max(p95(status), p95(wallet))` with `warm_runs=5` are **withdrawn** as methodologically invalid.

## Purpose

Establish reproducible p50/p95/max latency for dashboard-critical **read-only API** routes
**before** P2.5 optimizations (Issues #96–#103).

## Methodology (corrected)

| Rule | Detail |
|------|--------|
| Warm runs | Default **20** (p95 is an order statistic; with n=5 it collapses to ~max) |
| Overview | `overview_parallel_status_wallet`: per iteration, **concurrent** GET status+wallet; record **wall-clock** until both complete |
| Response size | Recorded as `response_bytes_p50` / `response_bytes_max` per endpoint |
| `optimization_applied` | `false` for #95 baseline; set `--optimization-applied` only on after-runs |
| Summary endpoint | Optional via `--include-summary` (Issue #98) |

### Out of scope for #95 (tracked elsewhere)

- Next.js SSR / dashboard page timing
- Playwright login → Overview/Positions/Fills/Equity (Issue #102)
- DB `query_count` / `db_ms` (Issue #96)
- `EXPLAIN ANALYZE` / indexes (Issue #101)
- Railway CPU/RAM counters (append in JSON `environment_notes.railway_resources`)

## How to measure

```bash
export PAPER_TRADING_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/paper_trading_test
export PAPER_API_BASE_URL=http://127.0.0.1:8080
export P2_BASELINE_GIT_REF=main
python scripts/measure_dashboard_api_baseline.py \
  --cold-runs 3 \
  --warm-runs 20 \
  --output docs/operations/dashboard-performance-baseline.json
```

After #98 (optional summary + mark after-run):

```bash
python scripts/measure_dashboard_api_baseline.py \
  --include-summary \
  --optimization-applied \
  --warm-runs 20 \
  --output docs/operations/dashboard-summary-after-98.json
```

## Measured results

### Local main (`main`), PostgreSQL `paper_trading_test`

Earlier warm_runs=5 table (status 96 ms / wallet 70 ms) remains archived in git history as a
**low-confidence** sample. Re-run with `--warm-runs 20` and parallel overview before claiming
budgets or improvement percentages. Update the JSON artifact and this table after that run.

| Metric | Value | Notes |
|--------|-------|-------|
| Parallel overview warm p95 | _pending re-measure_ | Required before any % improvement claim |
| status / wallet / tables | see JSON when refreshed | — |

Full report: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)

### Production-like (Railway)

Append after measuring against private Railway URL. Record region, resources, replica count,
and date in JSON `environment_notes`. Do not commit credentials.

## P2.5 budgets (ROADMAP)

| Target | Budget |
|--------|--------|
| Overview warm p95 | < 1.5 s |
| `/api/v1/status`, `/api/v1/wallet` p95 | < 250 ms |
| Table endpoints p95 | < 500 ms |

## Artifacts

- Machine-readable: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)
- CI sample: `tests/fixtures/perf/baseline-sample.json`

## Non-scope

- No query changes, caching, or index migrations in this issue
- No Railway resource scaling without measurement evidence
