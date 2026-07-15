# Production dashboard acceptance checklist (P2.5 / Issue #103)

**Status:** Procedure template — **Issue #103 / PR #116 must not be closed until this checklist is completed on Railway production (or production-like staging) with a signed-off row below.**

Do not mark GitHub Issue #103 Done based on merged code alone. Deployment + manual acceptance are explicit gates.

## Environment

| Check | Expected |
|-------|----------|
| `PRIVATE_PAPER_API_URL` | Points to `paper-trading-api` private URL (not mock) |
| `SESSION_SECRET`, `AUTH_*` | Set on `paper-trading-dashboard` |
| Data source | PostgreSQL paper-trading DB (no mock fixtures) |

## Functional acceptance

- [ ] Login and logout work on desktop and mobile viewport
- [ ] Overview shows wallet, PnL, heartbeat age from real DB
- [ ] Status, positions, orders, fills, equity pages load without mock imports
- [ ] Stale heartbeat visually indicated when threshold exceeded
- [ ] API outage shows clear error (not fake READY)
- [ ] Reconciliation/readiness errors not displayed as READY
- [ ] Dashboard has no mutation or trading control endpoints

## Performance acceptance

- [ ] Baseline JSON from Issue #95 archived for production-like run (`docs/operations/dashboard-performance-baseline.json`)
- [ ] Issue #98 before/after summary measurement recorded (`docs/operations/dashboard-summary-before-after.md`)
- [ ] Warm p95 within ROADMAP budgets or documented ADR deviation
- [ ] Loading skeletons verified — see `docs/operations/dashboard-loading-states-proof.md` (Issue #100)
- [ ] Issue #102 postgres regression passed locally; optional Railway probe via `PAPER_RAILWAY_API_BASE_URL`
- [ ] Cache policy evidence reviewed (`docs/operations/cache-policy-evidence.md`, Issue #99)

## Issue closure gate

**Close Issue #103 only when:**

1. Stack PRs #108–#115 are merged and deployed to Railway paper monitoring.
2. Every checkbox in this document is checked or explicitly N/A with reason.
3. Sign-off table below is filled (date, deployed Git SHA, tester name).

Until then, leave Issue #103 open and PR #116 in draft or “awaiting acceptance” state.

## Security

- [ ] Browser bundle does not contain `PRIVATE_PAPER_API_URL` or DB URLs
- [ ] Read-only API rejects POST/PUT/DELETE (405)

## External access

- [ ] `https://bot.save-money.xyz` (or configured domain) reachable with auth
- [ ] Document test date, tester, and known limitations below

### Known limitations (fill on acceptance)

- _None recorded yet._

### Sign-off

| Field | Value |
|-------|-------|
| Date | |
| Git SHA | |
| Tester | |
