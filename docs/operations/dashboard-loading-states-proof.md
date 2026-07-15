# Dashboard loading states — documentation proof (Issue #100)

PR #114 is **documentation + CI static proof** that loading skeletons exist.
It does **not** yet prove slow-API UX, error states, or Desktop/Mobile behavior.

## What is proven (CI)

`tests/deploy/test_dashboard_bundle.py::test_dashboard_loading_states_exist`
asserts every monitored dashboard route ships a Next.js `loading.tsx` with
`PageSkeleton` or `Skeleton`:

| Route file | Purpose |
|------------|---------|
| `src/app/dashboard/loading.tsx` | Overview |
| `src/app/dashboard/status/loading.tsx` | Runtime status |
| `src/app/dashboard/wallet/loading.tsx` | Wallet |
| `src/app/dashboard/positions/loading.tsx` | Positions |
| `src/app/dashboard/orders/loading.tsx` | Orders |
| `src/app/dashboard/fills/loading.tsx` | Fills |
| `src/app/dashboard/stops/loading.tsx` | Stop events |
| `src/app/dashboard/scheduler/loading.tsx` | Scheduler runs |
| `src/app/dashboard/equity/loading.tsx` | Equity curve |
| `src/app/dashboard/incidents/loading.tsx` | Incidents / audit |

```powershell
python -m pytest tests/deploy/test_dashboard_bundle.py::test_dashboard_loading_states_exist -q
```

## What is NOT proven (still open)

| Gap | How to close |
|-----|--------------|
| Slow API / skeleton visibility | Manual or Playwright with artificial latency |
| Error / stale-data UX | Manual (#103) or Playwright failure injection |
| Desktop + mobile layout | Manual viewport checks in #103 checklist |

Treat #114 as a static existence gate. Behavioral acceptance lives in #103.

## Railway doc cross-reference

[`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md)
(Dashboard maturity → **Current**) records CI skeleton verification.
