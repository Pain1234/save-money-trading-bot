# Dashboard summary API — before/after measurement (Issue #98)

Evidence for PR #113: replacing parallel `/api/v1/status` + `/api/v1/wallet` overview fetches with a single `/api/v1/dashboard-summary` call.

## Methodology

| Field | Before (#95 / `main`) | After (#98) |
|-------|----------------------|-------------|
| Git ref | `main` | `feat/98-dashboard-summary-api` |
| Database | `paper_trading_test` (local PostgreSQL) | same |
| Cold / warm runs | 3 / 5 | 3 / 5 |
| Tool | `scripts/measure_dashboard_api_baseline.py` | same (`--include-summary`) |

Raw JSON:

- Before: [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json)
- After: [`dashboard-summary-after-98.json`](dashboard-summary-after-98.json)

## Overview load comparison

The dashboard overview previously issued **two parallel GETs** (status + wallet). Wall-clock time is bounded by the slower of the two (warm p95):

| Metric | Before (parallel) | After (summary) | Delta |
|--------|-------------------|-----------------|-------|
| Status warm p95 | 96.0 ms | — | — |
| Wallet warm p95 | 70.2 ms | — | — |
| **Effective overview warm p95** | **96.0 ms** (max of parallel) | **56.4 ms** (summary) | **−39.6 ms (−41%)** |
| Summary warm p95 | N/A (endpoint absent) | 56.4 ms | — |

## Budget check

P2.5 overview warm p95 budget: **1500 ms**. After measurement: **56.4 ms** — well within budget.

## Production / Railway note

Local PostgreSQL measurements above are production-like (same schema, Alembic head, seeded singleton rows). Railway production values should be re-recorded after deploy using the same script against the production read-only API URL; see Issue #103 acceptance checklist.
