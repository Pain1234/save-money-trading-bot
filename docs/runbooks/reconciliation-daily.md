# Daily Reconciliation Runbook (P2 / Issue #12)

Procedure to detect wallet/position/fill inconsistencies in paper trading before they
become S2 incidents.

**Owner:** solo maintainer
**Frequency:** Weekly minimum; daily during active soak (P6) or after any restart/incident
**Last verified:** 2026-07-14 (procedure documented; uses existing `verify_accounting_independent`)

---

## When to run

- Scheduled: every **Monday** (solo maintainer weekly cadence).
- Ad hoc: after worker restart, deploy, migration, or reconciliation alert.
- Required before P6 soak sign-off.

---

## Prerequisites

- Readonly API URL (`PRIVATE_PAPER_API_URL`) or direct DB read access.
- Initial equity from config: default `100000` (`paper_initial_equity`).
- Python environment with project installed.

---

## Step 1 — Runtime health

```bash
curl -s "$PRIVATE_PAPER_API_URL/readiness" | jq '.runtime_readiness, .entry_readiness, .reasons'
curl -s "$PRIVATE_PAPER_API_URL/api/v1/status" | jq '.display_status, .heartbeat_age_seconds'
```

**Pass:** `runtime_readiness == true`, heartbeat age ≤ 300s, no unexpected `kill_switch`.

**Fail:** Follow [worker restart](worker-restart.md) or [incident response](../incidents/README.md).

---

## Step 2 — Wallet vs independent reconstruction

Run accounting verification against the live database:

```powershell
$env:PAPER_TRADING_DATABASE_URL = "<your-database-url>"
python scripts/reconcile_accounting.py
```

**Pass:** prints `RECONCILIATION OK` (exit code 0).

**Fail:** S2 — stop worker on Railway (see [kill-switch](kill-switch.md)), file incident,
do not deploy strategy changes until resolved.

The same independent reconstruction is a startup readiness gate (AUD-P1-008). Recovery
must not transition to `READY` when it finds a mismatch: runtime remains `DEGRADED`,
entry readiness remains false, and audit event `ACCOUNTING_RECONCILIATION_INCIDENT`
captures the mismatch details. Treat that event like a failed manual reconciliation:
stop the worker, preserve the database state, and file an incident before restart.

Automated test reference: `tests/paper_trading/test_accounting_verification.py` (CI `postgres`).

---

## Step 3 — Open positions vs intents

Via API:

```bash
curl -s "$PRIVATE_PAPER_API_URL/api/v1/positions?limit=50" | jq '[.items[] | select(.status=="OPEN")] | length'
curl -s "$PRIVATE_PAPER_API_URL/api/v1/orders?limit=50" | jq '[.items[] | select(.status=="OPEN" or .status=="PENDING")] | length'
```

**Pass:** open position count ≤ configured max (3 symbols in V1); no orphan open orders
without matching position logic.

**Manual check:** each open position has `entry_intent_id` traceable in fills list.

---

## Step 4 — Funding marks (paper)

Funding is **disabled by default** (`funding_enabled: false`). If enabled later:

- Compare `wallet.total_funding` to sum of funding events.
- Document any mismatch in incident template.

For current V1 paper: note "N/A — funding disabled" in reconciliation log.

---

## Step 5 — Exchange reconciliation (live)

**N/A for paper trading.** Live exchange reconcile is P8 scope.

---

## Freeze entries criteria

Per [`docs/risk-specification.md`](../risk-specification.md):

| Condition | Action |
|-----------|--------|
| Wallet cash mismatch | ERROR, freeze entries |
| Duplicate fill keys detected | ERROR, freeze entries |
| Reconciliation mismatch | ERROR, freeze entries |
| Heartbeat stale > 2× threshold | DEGRADED — investigate before new deploy |

Production: stop worker via Railway ([kill-switch](kill-switch.md)). Local/dev: control API if enabled.

---

## Reconciliation log template

Record each run (issue comment, personal log, or `docs/incidents/` if failed):

```text
Date (UTC):
Environment: railway-paper
Runtime readiness: pass/fail
Accounting verify: pass/fail
Open positions: N
Notes:
```

---

## Related

- [`docs/operations/metrics.md`](../operations/metrics.md)
- [`docs/operations/idempotency-audit.md`](../operations/idempotency-audit.md)
- Risk R-007 in [`docs/RISK_REGISTER.md`](../RISK_REGISTER.md)
