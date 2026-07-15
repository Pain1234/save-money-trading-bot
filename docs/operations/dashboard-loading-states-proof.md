# Dashboard loading states — documentation proof (Issue #100)

PR #114 is satisfied by **automated bundle verification** plus this traceability note. No additional UI code is required when CI already proves skeleton coverage.

## CI proof

`tests/deploy/test_dashboard_bundle.py::test_dashboard_loading_states_exist` asserts every monitored dashboard route ships a Next.js `loading.tsx` with `PageSkeleton` or `Skeleton`:

| Route file | Purpose |
|------------|---------|
| `src/app/dashboard/loading.tsx` | Overview (uses `fetchDashboardSummary`) |
| `src/app/dashboard/status/loading.tsx` | Runtime status |
| `src/app/dashboard/wallet/loading.tsx` | Wallet |
| `src/app/dashboard/positions/loading.tsx` | Positions |
| `src/app/dashboard/orders/loading.tsx` | Orders |
| `src/app/dashboard/fills/loading.tsx` | Fills |
| `src/app/dashboard/stops/loading.tsx` | Stop events |
| `src/app/dashboard/scheduler/loading.tsx` | Scheduler runs |
| `src/app/dashboard/equity/loading.tsx` | Equity curve |
| `src/app/dashboard/incidents/loading.tsx` | Incidents / audit |

Run locally:

```powershell
python -m pytest tests/deploy/test_dashboard_bundle.py::test_dashboard_loading_states_exist -q
```

## Railway doc cross-reference

[`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md) (Dashboard maturity → **Current**) records that route-level skeletons are verified in CI.

## Acceptance

- [x] All listed routes have loading skeletons (CI)
- [x] Overview uses summary fetch (`test_dashboard_overview_uses_summary_fetch`)
- [x] Documented in railway maturity checklist
