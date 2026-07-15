# Dashboard and API performance baseline (P2.5 / Issue #95)

**Status:** Measurement procedure and artifact template. Re-run after environment changes.

## Purpose

Establish reproducible p50/p95/max latency for dashboard-critical read-only API routes **before** any P2.5 optimization (Issues #96–#103).

## How to measure

### Prerequisites

- Read-only API running (`python -m paper_trading.api_runner` or Railway `paper-trading-api`)
- PostgreSQL with paper state (local soak seed or Railway paper stack)
- Optional: dashboard for manual navigation timing (Playwright in Issue #102)

### Command

```bash
export PAPER_API_BASE_URL=http://127.0.0.1:8080
python scripts/measure_dashboard_api_baseline.py \
  --cold-runs 3 \
  --warm-runs 5 \
  --output docs/operations/dashboard-performance-baseline.json
```

Document Railway region and service resources in the JSON `environment_notes` or below when measuring production-like targets.

## Endpoints measured

| Name | Path |
|------|------|
| status | `/api/v1/status` |
| wallet | `/api/v1/wallet` |
| positions | `/api/v1/positions?limit=50` |
| orders | `/api/v1/orders?limit=50` |
| fills | `/api/v1/fills?limit=50` |
| equity | `/api/v1/equity?limit=100` |
| dashboard_summary | `/api/v1/dashboard-summary` |

## Initial P2.5 budgets (from ROADMAP)

| Target | Budget |
|--------|--------|
| Overview warm p95 | < 1.5 s |
| `/api/v1/status`, `/api/v1/wallet` p95 | < 250 ms |
| Table endpoints p95 | < 500 ms |

Compare measured warm p95 from the JSON report against these budgets. Document accepted deviations in `docs/DECISION_LOG.md`.

## Artifact

- Machine-readable: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json) (regenerate locally; not committed until a measured run is recorded)
- Sample structure for CI: `tests/fixtures/perf/baseline-sample.json`

## Non-scope

- No query changes, caching, or index migrations in this issue
- No Railway resource scaling without measurement evidence
