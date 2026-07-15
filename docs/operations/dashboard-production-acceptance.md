# Production dashboard acceptance checklist (P2.5 / Issue #103)

**Status:** Procedure template — execute against Railway paper stack when Issues #95–#102 are merged.

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

- [ ] Baseline JSON from Issue #95 archived for production-like run
- [ ] Warm p95 within ROADMAP budgets or documented ADR deviation
- [ ] Loading skeletons visible during slow fetches (Issue #100)
- [ ] Issue #102 regression report attached (reporting mode)

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
