# API/DB instrumentation overhead — Issue #96 / PR #111

## What is measured

Per request (read-only API):

- `total_ms` — wall clock in `PerformanceLoggingMiddleware`
- `db_ms` / `query_count` — Engine-level `before_cursor_execute` /
  `after_cursor_execute` listeners attached for the request lifetime

Listeners are removed in `get_db_session` `finally` via
`detach_engine_query_metrics`.

## Measured overhead (2026-07-15)

Host: local Windows · DB: PostgreSQL `paper_trading_test` ·
branch `perf/96-api-db-instrumentation`.

### 1) In-process listener cost (`SELECT 1`, n=1000)

| Mode | Median (us) | p95 (us) |
|------|-------------|----------|
| Without listeners | 91.0 | 160.3 |
| With listeners attached for the loop | 95.8 | 173.4 |
| **Delta (listener bookkeeping)** | **~4.7 us** | **~13.1 us** |

Attach + detach once (n=200): median **~7.7 us**, p95 **~8.3 us**.

For a typical dashboard route (single-digit queries) this is well under
**0.1 ms** total instrumentation bookkeeping — nowhere near the 250 ms
status/wallet p95 budgets.

### 2) API warm wall-clock before/after (same host/DB, warm_runs=20)

Compared `#95` corrected baseline (no instrumentation listeners) vs this
branch (instrumentation on) using the #95 measure harness against
`http://127.0.0.1:8091`.

| Endpoint | Before p95 (ms) | After p95 (ms) | Delta ms | Delta % |
|----------|-----------------|----------------|----------|---------|
| overview_parallel_status_wallet | 121.8 | 104.5 | -17.2 | -14% |
| status | 120.8 | 118.4 | -2.4 | -2% |
| wallet | 117.0 | 130.5 | +13.5 | +12% |
| positions | 93.3 | 130.7 | +37.4 | +40% |
| orders | 111.7 | 122.1 | +10.4 | +9% |
| fills | 102.7 | 66.0 | -36.7 | -36% |
| equity | 114.2 | 94.0 | -20.2 | -18% |

**Interpretation:** Host wall-clock deltas move both up and down and are
dominated by OS/DB noise at ~100 ms latency. There is **no consistent
>=5% regression** attributable to listeners (status -2%; overview improved).
Treat the **us microbenchmark** as the authoritative instrumentation cost;
use warm p95 only as a no-regression smoke check vs budgets (all remain
well under 250 / 500 / 1500 ms).

Raw after report: [`instrumentation-overhead-after.json`](instrumentation-overhead-after.json)

## How to reproduce

```bash
# Authoritative microbenchmark (this PR)
export PAPER_TRADING_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test
export PYTHONPATH=services
python scripts/measure_instrumentation_overhead.py --loops 1000

# Unit + postgres (Issue #96 tests)
python -m pytest tests/paper_trading/test_perf_instrumentation.py -q

# API warm smoke (instrumented branch; prefer same Python as the #95 baseline host)
export PAPER_API_BASE_URL=http://127.0.0.1:8091
python scripts/measure_dashboard_api_baseline.py --warm-runs 20 \
  --output docs/operations/instrumentation-overhead-after.json
```

Host wall-clock before/after can differ by Python version / OS noise; treat the
microbenchmark as authoritative for listener cost.

Gate before merge: if status/wallet warm p95 rises by more than ~5% **and**
stays above budget under repeated runs on the same host/Python, investigate
listener leakage (missing detach).
