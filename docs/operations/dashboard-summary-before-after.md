# Dashboard summary API — before/after measurement (Issue #98)

Evidence for PR #113: replacing parallel `/api/v1/status` + `/api/v1/wallet`
overview fetches with a single `/api/v1/dashboard-summary` call.

## Methodology correction

Earlier drafts compared `max(p95(status), p95(wallet))` with `warm_runs=5` to
summary p95 and claimed **−41%**. That claim is **withdrawn**:

1. With n=5, reported p95 collapses to ~max.
2. `max` of separately measured endpoint p95s is **not** the p95 of a concurrent
   overview request.

Required before re-publishing an improvement %:

```bash
# Before (main): parallel overview wall-clock
export P2_BASELINE_GIT_REF=main
python scripts/measure_dashboard_api_baseline.py --warm-runs 20 \
  --output docs/operations/dashboard-performance-baseline.json

# After (#98): include summary; do not invent % without parallel metric
export P2_BASELINE_GIT_REF=feat/98-dashboard-summary-api
python scripts/measure_dashboard_api_baseline.py --warm-runs 20 \
  --include-summary --optimization-applied \
  --output docs/operations/dashboard-summary-after-98.json
```

Compare `overview_parallel_status_wallet.warm.p95_ms` (before) to
`dashboard_summary.warm.p95_ms` (after).

## Archived low-confidence samples

| Artifact | Notes |
|----------|-------|
| [`dashboard-performance-baseline.json`](dashboard-performance-baseline.json) | main, warm_runs=5 — low confidence |
| [`dashboard-summary-after-98.json`](dashboard-summary-after-98.json) | summary warm ~56 ms — endpoint works; % delta invalid until re-run |

## Budget check (still valid)

P2.5 overview warm p95 budget: **1500 ms**. Summary samples so far are far
below that even with weak methodology; re-confirm with `--warm-runs 20`.

## Production / Railway

Re-measure against Railway private API after deploy; fill Issue #103 checklist.
