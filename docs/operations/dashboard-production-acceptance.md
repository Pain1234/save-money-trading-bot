# Production dashboard acceptance checklist (P2.5 / Issue #103)

**Status:** Railway production acceptance in progress — stack deployed; Playwright login smoke pending tester password.

Do not mark GitHub Issue #103 Done based on merged code alone. Deployment + manual acceptance are explicit gates.

## Environment

| Check | Expected | Result (2026-07-15) |
|-------|----------|---------------------|
| `PRIVATE_PAPER_API_URL` | Points to `paper-trading-api` private URL (not mock) | **Pass** — `http://paper-trading-api.railway.internal:8080` on `paper-trading-dashboard` |
| `SESSION_SECRET`, `AUTH_*` | Set on `paper-trading-dashboard` | **Pass** — `SESSION_SECRET`, `AUTH_USERNAME`, `AUTH_PASSWORD_HASH` present |
| Data source | PostgreSQL paper-trading DB (no mock fixtures) | **Pass** — worker + API use `paper-trading-postgres` plugin (no mock env vars) |

**Deployed Git SHA (Railway `graceful-compassion` / production):** `13a62f18d516dc50cbe0d1d3ba8764ed346311e1` (main, #108–#115 stack)

## Functional acceptance

- [ ] Login and logout work on desktop and mobile viewport — _pending Playwright smoke (tester password)_
- [ ] Overview shows wallet, PnL, heartbeat age from real DB — _pending authenticated route check_
- [ ] Status, positions, orders, fills, equity pages load without mock imports — _pending Playwright smoke_
- [ ] Stale heartbeat visually indicated when threshold exceeded — **N/A this session** (no stale heartbeat injected; covered by dashboard unit/UI tests on main)
- [ ] API outage shows clear error (not fake READY) — **N/A this session** (no controlled API outage; ErrorPanel paths covered in code review + tests)
- [ ] Reconciliation/readiness errors not displayed as READY — **Pass (code)** — `RUNTIME_UNSET` / readiness sentinel tests on main (#118)
- [x] Dashboard has no mutation or trading control endpoints — **Pass** — dashboard exposes only `/api/auth/login` and `/api/auth/logout`; trading API is private

## Performance acceptance

- [x] Baseline JSON from Issue #95 archived for production-like run (`docs/operations/dashboard-performance-baseline.json`) — **Pass (local)** — production Railway probe optional per #95 scope split
- [x] Issue #98 before/after summary measurement recorded (`docs/operations/dashboard-summary-before-after.md`)
- [x] Warm p95 within ROADMAP budgets or documented ADR deviation — **Pass (local baseline)** — see `dashboard-performance-baseline.md`
- [x] Loading skeletons verified — see `docs/operations/dashboard-loading-states-proof.md` (Issue #100)
- [x] Issue #102 postgres regression passed locally; optional Railway probe via `PAPER_RAILWAY_API_BASE_URL` — **Pass (CI perf-reporting on main)**
- [x] Cache policy evidence reviewed (`docs/operations/cache-policy-evidence.md`, Issue #99)

## Issue closure gate

**Close Issue #103 only when:**

1. Stack PRs #108–#115 are merged and deployed to Railway paper monitoring. — **Done** (deploy 2026-07-15T20:09Z)
2. Every checkbox in this document is checked or explicitly N/A with reason.
3. Sign-off table below is filled (date, deployed Git SHA, tester name).

Until then, leave Issue #103 open and PR #116 in draft or “awaiting acceptance” state.

## Security

- [x] Browser bundle does not contain `PRIVATE_PAPER_API_URL` or DB URLs — **Pass** — scanned login page Next.js chunks 2026-07-15
- [x] Read-only API rejects POST/PUT/DELETE (405) — **Pass** — `tests/paper_trading/test_readonly_api.py` on main

## External access

- [x] `https://bot.save-money.xyz` (or configured domain) reachable with auth — **Pass** — HTTPS 200 `/login`, `/dashboard` redirects to login
- [x] Document test date, tester, and known limitations below

### Known limitations (fill on acceptance)

- Production API latency baseline not re-measured on Railway private network (local baseline + CI regression only).
- Stale-heartbeat and API-outage UI not manually exercised on production without fault injection.

### Sign-off

| Field | Value |
|-------|-------|
| Date | 2026-07-15 |
| Git SHA | `13a62f18d516dc50cbe0d1d3ba8764ed346311e1` |
| Tester | Justin (Railway + external checks); Playwright login smoke pending |
