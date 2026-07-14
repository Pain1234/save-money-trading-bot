# Critical Operational Metrics (P2 / Issue #16)

Defines the metrics operators should monitor for paper trading on Railway. Maps each
metric to API fields and dashboard surfaces. No new instrumentation is required for
P2 — this documents what already exists.

**Owner:** solo maintainer
**Review cadence:** each phase exit; after S1/S2 incidents
**Related:** [`docs/runbooks/README.md`](../runbooks/README.md), Issue #16

---

## Summary table

| Metric | What it means | Warning threshold | Source | API / UI |
|--------|---------------|-------------------|--------|----------|
| Heartbeat age | Seconds since worker last persisted `runtime_state.heartbeat_at` | `> stale_runtime_threshold_seconds` (default 300s) | DB `runtime_state` | `/api/v1/status`, dashboard home |
| Runtime readiness | Worker healthy enough for monitoring (not necessarily new entries) | `runtime_readiness == false` | `ReadinessService` | `/readiness`, `/api/v1/status` |
| Entry readiness | Safe to open new paper entries | `entry_readiness == false` | `ReadinessService` | `/readiness` (full flags) |
| Display status | Operator-facing rollup | `DEGRADED` or `STOPPED` | readonly API inference | `/api/v1/status`, dashboard |
| DB fingerprint | Hash of host+database (no credentials) | Worker vs API mismatch in logs | `database_identity.py` | Worker logs only |
| Reconnect count | WebSocket reconnects since worker start | Sustained increase + `DEGRADED` | `market_data` runtime | Worker logs (`reconnect_count` in structured events) |
| Kill switch | Entries frozen (V1 FREEZE policy) | `true` unexpectedly | `runtime_state.kill_switch` | `/readiness`, `/api/v1/status` → `runtime.kill_switch` |
| Paused | Manual pause via control API | `true` during expected run | `runtime_state.paused` | `/readiness`, `/api/v1/status` → `runtime.paused` |

---

## Heartbeat age

**Definition:** `now - runtime.heartbeat_at` in seconds.

**Defaults** (`PaperTradingConfig`):

- `heartbeat_interval_seconds`: 30 — worker persists heartbeat on this interval
- `stale_runtime_threshold_seconds`: 300 — readiness fails when age exceeds this

**API fields:**

- `GET /api/v1/status` → `heartbeat_age_seconds`, `stale_heartbeat_threshold_seconds`, `runtime.heartbeat_at`
- `GET /readiness` → fails with reason `stale_heartbeat` when over threshold

Embedded worker API (local/dev only, `PAPER_API_ENABLED=true`): `GET /runtime` → `heartbeat_at`.
Readonly Railway API has **no** `/runtime` route.

**Dashboard:** [`src/lib/paper-api/client.ts`](../../src/lib/paper-api/client.ts) `fetchStatus()`;
home page shows heartbeat age and highlights when
`heartbeat_age_seconds > stale_heartbeat_threshold_seconds`.

**Worker logs:** `worker_liveness_heartbeat` events include `previous_heartbeat_at`,
`new_heartbeat_at`, `database_fingerprint`.

**SLA (solo paper ops):**

| Age | Interpretation | Action |
|-----|----------------|--------|
| ≤ 300s | Normal | None |
| 300s–600s | Stale / degraded | Check worker logs; see [worker restart](../runbooks/worker-restart.md) |
| > 600s or null runtime | Likely stopped | Verify Railway worker service; check advisory lock contention |

---

## Readiness states

**`runtime_readiness`:** process up, DB reachable, migrations at head, heartbeat fresh,
no fatal recovery state, scheduler not blocked by unrecoverable errors.

**`entry_readiness`:** `runtime_readiness` plus market data ready, not paused, kill switch
off, bridge backlog clear.

**API:** `GET /readiness` returns all flags:

```text
process_liveness, runtime_readiness, entry_readiness, market_data_ready,
database_ready, migration_at_head, advisory_lock_held, paused, kill_switch, reasons[]
```

HTTP 503 when `runtime_readiness` is false.

**Dashboard status rollup** (`/api/v1/status`):

| `display_status` | Condition |
|------------------|-----------|
| `READY` | `runtime_readiness == true` |
| `DEGRADED` | runtime exists but not ready |
| `STOPPED` | no runtime or `FAILED` |

**Common `reasons`:** `stale_heartbeat`, `migration_not_at_head`, `database_unreachable`,
`kill_switch`, `paused`, market-data degraded reasons from worker.

---

## Database fingerprint drift

**Definition:** SHA-256 fingerprint of PostgreSQL host + database name (credentials stripped).
Worker and readonly API must target the same database.

**Detection:**

1. Compare worker startup log `database_identity service_role=worker database_fingerprint=...`
   with API startup log `service_role=readonly-api database_fingerprint=...`.
2. Mismatch → S2 misconfiguration (API shows stale or empty state).

**Tests:** `tests/paper_trading/test_heartbeat_observability.py` — same fingerprint across
URLs with different credentials.

**Action:** Fix `PAPER_TRADING_DATABASE_URL` on the misconfigured service; redeploy.

---

## Market-data reconnect count

**Definition:** Monotonic counter on Hyperliquid WebSocket transport (`reconnect_count`).
Incremented on each transport reconnect attempt.

**Log events** (filter worker logs):

| `event_type` | Meaning |
|--------------|---------|
| `market_data_reconnect_started` | Reconnect attempt beginning |
| `market_data_transport_reconnect_succeeded` | WS transport restored |
| `market_data_reconnect_timeout` | Exceeded `reconnect_total_timeout_seconds` (default 120s) |
| `market_data_reconnect_failed` | Reconnect error |
| `market_data_reconnect_degraded` | Reconnect completed but readiness degraded |

**API proxy:** `GET /api/v1/market-data` exposes `market_data_ready`, `worker_heartbeat_at`,
`worker_status` — not reconnect count directly. Use logs for reconnect frequency.

**Warning:** More than 3 reconnects per hour sustained, or any `reconnect_degraded` with
`entry_readiness == false` for > 15 minutes.

**Related risk:** R-001, R-010 in [`docs/RISK_REGISTER.md`](../RISK_REGISTER.md).

---

## Kill switch and pause (Railway production)

Control API is **disabled** on worker and readonly API (`PAPER_CONTROL_API_ENABLED=false`).
Production freeze: **stop worker** in Railway. See [kill-switch runbook](../runbooks/kill-switch.md).

**Observe state (readonly API):**

- `GET /readiness` → `kill_switch`, `paused`, `entry_readiness`
- `GET /api/v1/status` → `runtime.kill_switch`, `runtime.paused`

Local/dev control API requires `PAPER_API_ENABLED=true` on worker process only.

---

## Recommended monitoring checklist (manual / dashboard)

Daily (or before trusting new deploy):

1. Dashboard home — heartbeat age green, `display_status == READY`.
2. `GET /readiness` — `entry_readiness == true` if entries expected.
3. Scan worker logs for `runtime_heartbeat_failed` or `market_data_reconnect_failed`.
4. Confirm worker and API `database_fingerprint` match (after any URL change).

Weekly:

5. Run [daily reconciliation](../runbooks/reconciliation-daily.md) (minimum weekly for solo ops).
6. Verify Railway Postgres backup age in Railway dashboard.

---

## CI regression coverage

| Metric area | Test file | CI job |
|-------------|-----------|--------|
| Heartbeat / fingerprint | `test_heartbeat_observability.py` | `postgres` |
| Readiness promotion | `test_readiness_promotion.py`, `e2e/test_api_e2e.py` | `postgres` |
| Reconnect readiness | `tests/market_data/test_reconnect_readiness.py` | `test-market-data` |

---

## Last updated

- **2026-07-14** — Initial P2 metrics catalog (Issue #16).
