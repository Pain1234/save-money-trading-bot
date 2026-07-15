# Dashboard and API performance baseline (P2.5 / Issue #95)

**PR #108 scope:** Read-only **API** measurement harness + corrected local API baseline
artifact. This is the mergeable slice of #95.

**Remaining Issue #95 work (tracked, not claimed done by #108):**

| Remaining AC | Tracked in |
|--------------|------------|
| Next.js SSR / dashboard page timing | Follow-up after #98/#100; Playwright #102 |
| DB `query_count` / `db_ms` baseline | Issue #96 instrumentation + re-measure |
| Railway resource / production URL sample | Issue #103 (fill `environment_notes`) |
| EXPLAIN / index evidence | Issue #101 |

Prior `max(p95(status), p95(wallet))` / warm_runs=5 “−41%” claims are **withdrawn**.

## Purpose

Reproducible p50/p95/max latency for dashboard-critical **read-only API** routes
**before** P2.5 optimizations (Issues #96–#103).

## Methodology (corrected)

| Rule | Detail |
|------|--------|
| Warm runs | Default **20** |
| Overview | `overview_parallel_status_wallet`: concurrent GET status+wallet wall-clock |
| Response size | `response_bytes_p50` / `response_bytes_max` |
| `optimization_applied` | `false` for this baseline |
| Summary endpoint | Optional `--include-summary` (Issue #98) |

## How to measure

```bash
export PAPER_TRADING_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/paper_trading_test
export PAPER_API_BASE_URL=http://127.0.0.1:8090
export P2_BASELINE_GIT_REF=perf/95-dashboard-api-baseline
python scripts/measure_dashboard_api_baseline.py \
  --cold-runs 3 \
  --warm-runs 20 \
  --output docs/operations/dashboard-performance-baseline.json
```

## Measured results (corrected)

### Local PostgreSQL `paper_trading_test` — 2026-07-15

Git ref: `perf/95-dashboard-api-baseline` · `--warm-runs 20` · parallel overview on ·
`http://127.0.0.1:8090`

| Endpoint | Warm p50 (ms) | Warm p95 (ms) | Response bytes p50 |
|----------|---------------|---------------|--------------------|
| overview_parallel_status_wallet | — | **121.8** | 923 |
| status | — | 120.8 | 684 |
| wallet | — | 117.0 | 238 |
| positions | — | 93.3 | 42 |
| orders | — | 111.7 | 42 |
| fills | — | 102.7 | 42 |
| equity | — | 114.2 | 43 |

Full report: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)

### Production-like (Railway)

Still pending — append under Issue #103 with region/resources; do not commit secrets.

## P2.5 budgets (ROADMAP)

| Target | Budget | Local status |
|--------|--------|--------------|
| Overview warm p95 | < 1.5 s | 121.8 ms — pass |
| status / wallet p95 | < 250 ms | pass |
| Table endpoints p95 | < 500 ms | pass |

## Artifacts

- Machine-readable: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)
- CI sample: `tests/fixtures/perf/baseline-sample.json`

## Non-scope for this PR

- No query changes, caching, or index migrations
- No Railway resource scaling without measurement evidence
