# Dashboard and API performance baseline (P2.5 / Issue #95)

**Status:** Measured against `main` before P2.5 optimizations (2026-07-15).

## Purpose

Establish reproducible p50/p95/max latency for dashboard-critical read-only API routes **before** any P2.5 optimization (Issues #96–#103).

## How to measure

### Prerequisites

- Read-only API running (`python -m paper_trading.api_runner` or Railway `paper-trading-api`)
- PostgreSQL with paper state (local soak seed or Railway paper stack)
- Measure **main branch** code: `git checkout main` or set `P2_BASELINE_GIT_REF=main`

### Command

```bash
export PAPER_TRADING_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/paper_trading_test
export PAPER_API_BASE_URL=http://127.0.0.1:8080
export P2_BASELINE_GIT_REF=main
python scripts/measure_dashboard_api_baseline.py \
  --cold-runs 3 \
  --warm-runs 5 \
  --output docs/operations/dashboard-performance-baseline.json
```

`/api/v1/dashboard-summary` is **optional** until Issue #98 merges:

```bash
python scripts/measure_dashboard_api_baseline.py --include-summary ...
```

Document Railway region and service resources in the JSON `environment_notes` when measuring production-like targets.

## Endpoints measured (default)

| Name | Path |
|------|------|
| status | `/api/v1/status` |
| wallet | `/api/v1/wallet` |
| positions | `/api/v1/positions?limit=50` |
| orders | `/api/v1/orders?limit=50` |
| fills | `/api/v1/fills?limit=50` |
| equity | `/api/v1/equity?limit=100` |

Optional (Issue #98): `dashboard_summary` → `/api/v1/dashboard-summary`

## Measured results

### Local main (`main` @ pre-P2.5), PostgreSQL `paper_trading_test`

Measured **2026-07-15** against `main` read-only API (`http://127.0.0.1:8088`), empty paper tables, Windows dev host.

| Endpoint | Warm p50 (ms) | Warm p95 (ms) | Warm max (ms) |
|----------|---------------|---------------|---------------|
| status | 56.7 | 96.0 | 96.0 |
| wallet | 45.2 | 70.2 | 70.2 |
| positions | 43.7 | 70.8 | 70.8 |
| orders | 41.5 | 91.9 | 91.9 |
| fills | 40.5 | 101.8 | 101.8 |
| equity | 42.6 | 88.9 | 88.9 |

Full report: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)

### Production-like (Railway paper-trading-api)

Append after measuring against private Railway URL (`PRIVATE_PAPER_API_URL` or internal service URL). **Do not commit credentials.** Record region, replica count, and date in JSON `environment_notes`.

## Initial P2.5 budgets (from ROADMAP)

| Target | Budget |
|--------|--------|
| Overview warm p95 | < 1.5 s |
| `/api/v1/status`, `/api/v1/wallet` p95 | < 250 ms |
| Table endpoints p95 | < 500 ms |

Compare measured warm p95 from the JSON report against these budgets. Document accepted deviations in `docs/DECISION_LOG.md`.

## Artifacts

- Machine-readable: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)
- Sample structure for CI: `tests/fixtures/perf/baseline-sample.json`

## Non-scope

- No query changes, caching, or index migrations in this issue
- No Railway resource scaling without measurement evidence
