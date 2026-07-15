# API/DB instrumentation overhead — Issue #96 / PR #111

## What is measured

Per request (read-only API):

- `total_ms` — wall clock in `PerformanceLoggingMiddleware`
- `db_ms` / `query_count` — Engine-level `before_cursor_execute` /
  `after_cursor_execute` listeners attached for the request lifetime

Listeners are removed in `get_db_session` `finally` via
`detach_engine_query_metrics`.

## Overhead expectation

Cursor event listeners add a few microseconds of Python bookkeeping per SQL
statement. They do **not** change SQL or connection pooling. For typical dashboard
routes (single-digit query counts), overhead should remain well under 1 ms and
must not approach the P2.5 status/wallet budgets (250 ms p95).

## How to verify

```bash
# Unit + postgres (Issue #96 tests)
python -m pytest tests/paper_trading/test_perf_instrumentation.py -q

# Compare API warm p95 with instrumentation present (this branch) vs main
# using scripts/measure_dashboard_api_baseline.py --warm-runs 20
```

Document any measured delta in PR notes before merge. If warm p95 increases by
more than ~5% vs the #95 baseline under the same host/DB, investigate listener
leakage (missing detach) before merging.
