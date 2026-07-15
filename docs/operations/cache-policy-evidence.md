# Cache policy evidence (Issue #99)

Gate for PR #112: `Cache-Control` TTLs are justified by measured API latency from Issues #95 and #98, not arbitrary defaults.

## Source measurements

| Artifact | Git ref | Key warm p95 values |
|----------|---------|-------------------|
| [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json) | `main` | status 96 ms, wallet 70 ms |
| [`dashboard-summary-after-98.json`](dashboard-summary-after-98.json) | `feat/98` | dashboard-summary 56 ms |

See also [`dashboard-summary-before-after.md`](dashboard-summary-before-after.md).

## TTL decisions

| Route group | TTL (s) | Rationale |
|-------------|---------|-----------|
| `/api/v1/status`, `/api/v1/market-data`, `/api/v1/dashboard-summary` | **2** | Warm p95 ≤ 96 ms. A 2 s private cache caps repeat load at ~0.5 req/s per tab while keeping heartbeat/status fresh enough for a monitoring dashboard. Summary replaces parallel status+wallet (56 ms vs 96 ms effective overview). |
| `/api/v1/wallet`, `/api/v1/positions` | **5** | Warm p95 70–96 ms on main; slightly longer cache acceptable for slower-changing portfolio slices still fetched on detail routes. |
| `/api/v1/orders`, `/api/v1/fills` | **5** | Warm p95 ≤ 102 ms; tables refresh on tab focus with moderate staleness tolerance. |
| `/api/v1/equity`, `/api/v1/events`, `/api/v1/scheduler-runs` | **30** | Warm p95 ≤ 95 ms; historical / audit data changes infrequently. |
| `/health`, `/readiness` | **none** | Probes must reflect live dependency state; excluded from cache middleware. |

## Approval criteria met

- [x] TTLs derived from documented warm p95 measurements (not guesswork)
- [x] Overview path (`dashboard-summary`) measured after #98 at 56 ms warm p95 — within 1500 ms budget with headroom for 2 s cache
- [x] Health/readiness excluded from caching
- [ ] Railway production re-measurement after deploy (tracked under Issue #103)

## Re-validation

Re-run after stack merge or schema changes:

```powershell
$env:PAPER_API_BASE_URL="http://127.0.0.1:8080"
python scripts/measure_dashboard_api_baseline.py --include-summary --warm-runs 5 --cold-runs 3
```

If warm p95 for any 2 s-cached route exceeds **500 ms**, reduce TTL or investigate before merging cache policy changes.
