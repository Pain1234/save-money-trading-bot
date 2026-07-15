# Dashboard performance regression — Issue #102 / PR #115

## CI policy

| Job | Marker / command | Gate? |
|-----|------------------|-------|
| `test` (unit) | `not reporting` | exclude reporting |
| `perf-reporting` | `pytest tests/perf -m "reporting and postgres"` | **functional hard** + latency **soft** + artifact |
| Playwright (manual/release) | `npm run test:dashboard-perf` | optional env |

**Latency is report-only.** Budget breaches are written to
`budget_comparisons` / `latency_budget_breach` in the JSON artifact and
printed to the log. They do **not** fail the `perf-reporting` job.
Hard fails remain: HTTP non-200, missing schema fields, missing artifact.

## Playwright (Node `@playwright/test`)

Uses existing package.json dependency — **not** Python `playwright`.

```bash
export PAPER_DASHBOARD_BASE_URL=https://bot.example
export PAPER_DASHBOARD_USER=monitor
export PAPER_DASHBOARD_PASSWORD=...
npm ci
npx playwright install chromium
npm run test:dashboard-perf
```

Selectors: `getByLabel("Username")` / `getByLabel("Password")` (LoginForm wraps
inputs in labels; `name="username"|"password"` also present).

Each `page.goto()` asserts `response.ok()` and a route-specific heading
(Overview / Positions / Fills / Equity History).

Pytest wrapper (same env): `test_node_playwright_dashboard_routes_when_configured`
shells out to `npx playwright test -c playwright.perf.config.ts`.

## Artifact (CI)

Job `perf-reporting` uploads `dashboard-perf-regression-report.json` when the
postgres reporting tests write it (`test_postgres_core_endpoints_warm_p95_artifact`).

Locally:

```bash
export PAPER_TRADING_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test
python -m pytest tests/perf -m "reporting and postgres" -q
# → docs/operations/dashboard-perf-regression-report.json
```

## Acceptance map

| AC | Evidence |
|----|----------|
| Core API endpoints measured | `test_postgres_core_endpoints_warm_p95_artifact` |
| Real PostgreSQL | `@requires_postgres` / CI `perf-reporting` |
| Optional Railway | `test_railway_dashboard_summary_when_configured` |
| Playwright login→routes | `tests/e2e/dashboard-routes.spec.ts` + `npm run test:dashboard-perf` |
| CI artifact | `actions/upload-artifact` ← `dashboard-perf-regression-report.json` |
| No flaky latency gate | Soft `budget_comparisons` in artifact (`latency_gate: soft`) |

## Caveat

Reporting warm_runs default to 5 (p95≈max). Prefer
`scripts/measure_dashboard_api_baseline.py --warm-runs 20` for published numbers.
