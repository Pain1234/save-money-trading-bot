# Dashboard SQL query audit (P2.5 / Issue #101)

**Status:** Analysis checklist and repository query map. Run `EXPLAIN ANALYZE` against a production-like dataset before adding indexes.

## Scope

Read-only dashboard API queries invoked from:

- `services/paper_trading/readonly_api.py`
- `services/paper_trading/repository.py` (`list_*`, `get_*`)

## Queries to profile

| Route | Repository methods | Notes |
|-------|-------------------|--------|
| `/api/v1/status` | `get_runtime_state`, readiness evaluation | Single snapshot after Issue #97 |
| `/api/v1/dashboard-summary` | snapshot + `get_wallet`, `get_open_positions` | One overview round-trip |
| `/api/v1/wallet` | `get_wallet` | Singleton row |
| `/api/v1/positions` | `list_positions` | Keyset on `opened_at`, `position_id` |
| `/api/v1/orders` | `list_orders` | Keyset on `created_at`, `paper_order_id` |
| `/api/v1/fills` | `list_fills` | Keyset on `fill_time`, `fill_id` |
| `/api/v1/equity` | `list_portfolio_snapshots` | Keyset on `evaluation_time`, `snapshot_id` |
| `/api/v1/events` | `list_audit_events` | History table growth risk |
| `/api/v1/scheduler-runs` | `list_scheduler_runs` | History table growth risk |

## EXPLAIN ANALYZE procedure

1. Seed representative data (`scripts/run_paper_soak.py` or restore drill seed).
2. Connect to the same database URL as the read-only API.
3. Capture SQLAlchemy echo or log statements for each route (after Issue #96 instrumentation).
4. Run `EXPLAIN (ANALYZE, BUFFERS)` for each distinct statement.
5. Record p95 `Execution Time` and whether `Seq Scan` appears on growing tables.

## Index candidates (apply only with evidence)

| Table pattern | Candidate index | Trigger |
|---------------|-----------------|---------|
| Fills history | `(fill_time DESC, fill_id DESC)` | Seq scan on `/api/v1/fills` |
| Orders history | `(created_at DESC, paper_order_id DESC)` | Seq scan on `/api/v1/orders` |
| Equity snapshots | `(evaluation_time DESC, snapshot_id DESC)` | Seq scan on `/api/v1/equity` |
| Audit events | `(created_at DESC, event_id DESC)` | Seq scan on `/api/v1/events` |

**Write overhead:** document insert rate on worker path before adding composite indexes.

## Issue #97 interaction

Status and readiness share `_runtime_readiness_snapshot()` — expect **one** `get_runtime_state()` per status/summary request after refactor. Compare `query_count` in perf logs before/after.

## Deliverables

- [ ] EXPLAIN output attached to Issue #101 or PR
- [ ] Index migration only if seq scan confirmed on ≥10k row tables
- [ ] No schema change without Alembic issue scope
