# Idempotency Audit (P2 / Issue #13)

Inventory of critical processing paths, their duplicate-safety mechanisms, test coverage,
and gaps. **No trading logic changes** — audit only.

**Date:** 2026-07-14
**Reviewer:** P2 operational reliability work
**Related:** Issue #13, Issue #14, [`docs/operations/metrics.md`](metrics.md)

---

## Legend

| Status | Meaning |
|--------|---------|
| **Covered** | Postgres integration or E2E test in CI `postgres` job |
| **Unit only** | Mock/unit test; DB behavior inferred from code |
| **Gap** | Missing test or mechanism needs follow-up issue |

---

## Audit table

| Path | Mechanism | Unique constraint / API | Test coverage | Status |
|------|-----------|---------------------------|---------------|--------|
| Strategy evaluations | `insert_or_get_strategy_evaluation` | evaluation uniqueness by symbol + time + version | `replay/test_replay_idempotency.py::test_double_evaluation_produces_single_row` | **Covered** |
| Trade intents | `insert_or_get_trade_intent` | `idempotency_key` unique | `replay/test_replay_idempotency.py`, `e2e/test_restart_lifecycle.py::test_crash_after_intent_no_duplicate_on_retry` | **Covered** |
| Paper orders | `insert_or_get_paper_order` | order linked to intent | `integration/test_postgres_repository.py::test_duplicate_fill_insert` (order setup only; asserts fill dedup, not order count) | **Unit only** |
| Paper fills | `insert_or_get_paper_fill` | `deterministic_fill_key` / fill dedup | `replay/test_replay_idempotency.py::test_double_fill_produces_single_fill`, `e2e/test_restart_lifecycle.py::test_fill_idempotent_after_simulated_restart` | **Covered** |
| Stop events | `insert_or_get_stop_event` | idempotency key per stop evaluation | `test_stop_lifecycle.py` (mock repo only) | **Unit only** |
| Funding events | `insert_or_get_funding_event` | idempotency key | `test_ids.py::test_funding_and_scheduler_keys` (key format only); `funding_enabled=false` in V1 | **Unit only** |
| Scheduler runs | `insert_or_get_scheduler_run` | `idempotency_key` unique | `integration/test_scheduler_transactions.py`, `test_postgres_database_safety.py` | **Covered** |
| Recovery scheduler rows | recovery job reuses `scheduler_run_key` | same as scheduler runs | `integration/test_recovery_postgres.py`, `test_degraded_startup_recovery.py`, `test_runtime_recovery.py`, `e2e/test_restart_lifecycle.py::test_recovery_after_orphan_scheduler_run` | **Covered** |
| Gap-fill delay jobs | `scheduler_run_key(job, scheduled_for)` | scheduler idempotency | `test_gap_fill_delay_phases.py` | **Covered** |
| Market event bridge jobs | `insert_or_get_scheduler_run` | scheduler idempotency | `test_market_event_bridge_completion.py` | **Covered** |
| Portfolio snapshots | `insert_or_get_portfolio_snapshot` + `ON CONFLICT DO NOTHING` on `idempotency_key` | DB unique on `idempotency_key` | `test_portfolio_snapshots.py` (mock only) | **Unit only** |
| Control API run-cycle | `scheduler_run_key` before insert | rejects duplicate scheduled run | `e2e/test_api_e2e.py::test_api_run_cycle_idempotent` | **Covered** |
| Wallet updates | transactional scope; crash rolls back | N/A (single row version) | `failure/test_crash_boundaries.py::test_crash_after_wallet_update_rolls_back` | **Covered** |
| Advisory lock | Postgres advisory lock single holder | lock ID in config | `test_postgres_database_safety.py`, `failure/test_scheduler_contention.py` | **Covered** |
| Startup recovery | orphan `RUNNING` scheduler → failed + retry | recovery policy | `integration/test_recovery_postgres.py`, `test_degraded_startup_recovery.py`, `test_runtime_recovery.py`; `test_recovery.py` (unit/mock policy checks only) | **Covered** |

---

## Paper orders — accepted residual risk (V1)

**Code path:** `insert_or_get_paper_order` deduplicates by intent linkage.

**Why unit only:** Postgres fill dedup is tested (`test_duplicate_fill_insert`), but no test
asserts duplicate order insert returns `(row, created=False)` or stable order count on retry.
Fill/idempotency E2E covers economic outcome indirectly.

**Decision:** Accept for P2. Optional follow-up: postgres duplicate-order test.

---

## Stop and funding — accepted residual risk (V1)

**Stop events:** `test_stop_lifecycle.py` uses `MagicMock` repository — no postgres assertion
that `insert_or_get_stop_event` deduplicates. Economic risk is lower than fills (stop updates
are idempotent by position state). Optional follow-up: postgres test in gap-fill/stop integration.

**Funding events:** Funding is **disabled** in production config (`PAPER_FUNDING_ENABLED=false`).
Only idempotency **key format** is tested. No postgres insert test until funding is enabled (P6+).

**Decision:** Accept for P2. No bug issue filed.

---

## Portfolio snapshot — accepted residual risk

**Code path:** `repository.insert_or_get_portfolio_snapshot` uses
`on_conflict_do_nothing(index_elements=[PortfolioSnapshotRow.idempotency_key])`.

**Why unit only:** `test_portfolio_snapshots.py` mocks the repository; no postgres test
asserts double-insert returns `(row, created=False)`.

**Risk assessment:** Low — snapshots are observability artifacts, not economic truth.
Duplicate snapshot would not double-apply fills or wallet changes.

**Decision:** Accept for P2. Optional P3+ enhancement: add postgres test mirroring
`test_double_fill_produces_single_fill`. **No bug issue filed.**

---

## Worker restart scenario (Issue #14 cross-reference)

Simulated restart coverage (CI `postgres` job):

| Scenario | Test |
|----------|------|
| Orphan RUNNING scheduler row | `e2e/test_restart_lifecycle.py::test_recovery_after_orphan_scheduler_run` |
| Crash after intent (rollback) | `e2e/test_restart_lifecycle.py::test_crash_after_intent_no_duplicate_on_retry` |
| Double fill after restart | `e2e/test_restart_lifecycle.py::test_fill_idempotent_after_simulated_restart` |
| Transaction edge crashes | `failure/test_crash_boundaries.py` |

**Not covered in CI:** real SIGKILL on Railway with live advisory lock. Mitigated by
[worker restart runbook](../runbooks/worker-restart.md) and advisory lock + idempotency above.

---

## Bugs filed from this audit

None. Critical economic paths (intents, fills, scheduler runs) have postgres integration
coverage. Paper orders, portfolio snapshots, stop/funding paths documented as unit only or
accepted residual risk above.

---

## Recommendations

1. Before P6 soak, consider postgres test for portfolio snapshot idempotency (nice-to-have).
2. On any duplicate-fill S2 incident, re-run this audit and add row for root cause path.
3. Link new paths to idempotency keys in PR description when adding scheduler jobs.

---

## Last updated

- **2026-07-14** — Initial audit (Issue #13).
