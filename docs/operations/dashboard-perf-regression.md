# Dashboard performance regression — Issue #102 / PR #115

## CI policy

`pytest.mark.reporting` tests are **not** merge gates. The unit job uses:

```text
-m "not postgres and not live and not soak and not reporting"
```

Run manually / release gate:

```bash
export PAPER_TRADING_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test
python -m pytest tests/perf -m reporting -q
```

Optional Railway / Playwright:

```bash
export PAPER_RAILWAY_API_BASE_URL=https://...
export PAPER_DASHBOARD_BASE_URL=https://bot.save-money.xyz
export PAPER_DASHBOARD_USER=...
export PAPER_DASHBOARD_PASSWORD=...
python -m pytest tests/perf -m reporting -q
```

## Artifact

Postgres reporting runs write `docs/operations/dashboard-perf-regression-report.json`
(warm p95 per core endpoint). Commit after a release measurement if desired.

## Acceptance map

| AC | Evidence |
|----|----------|
| Core API endpoints measured | `test_postgres_core_endpoints_warm_p95_artifact`, `test_core_endpoints_return_200` |
| Real PostgreSQL | `@requires_postgres` tests |
| Optional Railway | `test_railway_dashboard_summary_when_configured` |
| Playwright login→routes | `test_playwright_dashboard_routes_when_configured` (skip without env) |
| CI artifact | `dashboard-perf-regression-report.json` when reporting job runs |

## Caveat

With `warm_runs=5` in reporting tests, p95 ≈ max. Prefer
`scripts/measure_dashboard_api_baseline.py --warm-runs 20` for published numbers.
