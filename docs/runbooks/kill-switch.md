# Kill Switch Runbook (P2)

Freeze new paper entries. V1 policy: `KillSwitchClosePolicy.FREEZE` (no market closes).

**Owner:** solo maintainer
**Policy:** FREEZE only
**Last verified:** 2026-07-14
**Spec:** [`docs/risk-specification.md`](../risk-specification.md)

---

## Railway production (default configuration)

Production worker and readonly API run with control routes **disabled**:

| Service | `PAPER_API_ENABLED` | `PAPER_CONTROL_API_ENABLED` |
|---------|---------------------|-----------------------------|
| Worker | `false` | `false` |
| Readonly API | n/a | `false` (hard requirement in `api_runner.py`) |

The worker has **no public HTTP port** on Railway. `POST /control/kill` is **not reachable**
in this setup. Use the production path below.

### Production — freeze entries (stop worker)

1. Railway → `paper-trading-worker` → **Stop** or scale replicas to **0**.
2. Verify processing stopped via readonly API (private URL):

   ```bash
   curl -s "$PRIVATE_PAPER_API_URL/api/v1/status" | jq '.display_status, .heartbeat_age_seconds'
   curl -s "$PRIVATE_PAPER_API_URL/readiness" | jq '.entry_readiness, .runtime_readiness, .reasons'
   ```

   Expect `display_status` `DEGRADED` or `STOPPED`; heartbeat age grows beyond threshold.

3. Run [reconciliation](reconciliation-daily.md) before restarting worker if economic state is suspect.
4. Preserve Railway worker logs and note Postgres backup timestamp ([backup-restore](backup-restore.md)).

**Observe flags (readonly API only):** `/readiness` exposes `kill_switch` and `paused` from DB
runtime state. There is **no** `/runtime` route on the readonly API — use `/api/v1/status`
(`runtime.kill_switch`, `runtime.paused`) or `/readiness`.

---

## Local / dev — control API path

Enable embedded API on the worker process (never on the readonly API service):

```powershell
$env:PAPER_API_ENABLED = "true"
$env:PAPER_CONTROL_API_ENABLED = "true"
$env:PAPER_CONTROL_API_KEY = "<local-secret>"
python -m paper_trading
```

Activate kill switch (localhost only unless you explicitly expose the port):

```bash
curl -X POST "http://127.0.0.1:8080/control/kill" \
  -H "X-API-Key: $PAPER_CONTROL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected:** `{"accepted": true, "message": "kill switch enabled"}`

**Rejected:** `CLOSE_AT_NEXT_OPEN` returns HTTP 422 — not supported in paper V1.

Verify locally:

```bash
curl -s "http://127.0.0.1:8080/readiness" | jq '.kill_switch, .entry_readiness'
```

Tests: `tests/paper_trading/e2e/test_pause_kill_lifecycle.py` (CI `postgres`).

---

## Resume after kill switch

Kill switch is **persistent**. There is no `/control/unkill` in V1.

`POST /control/resume` returns **409** while kill switch is active (local/dev only).

Production resume: restart worker after reconciliation; if `kill_switch` remains set in DB,
follow manual recovery in [`docs/risk-specification.md`](../risk-specification.md) with human approval.

---

## Pause (local/dev alternative)

Temporary stop without permanent kill (requires control API enabled as above):

```bash
curl -X POST "http://127.0.0.1:8080/control/pause" -H "X-API-Key: $PAPER_CONTROL_API_KEY"
curl -X POST "http://127.0.0.1:8080/control/resume" -H "X-API-Key: $PAPER_CONTROL_API_KEY"
```

Production equivalent: stop worker (same as kill-switch production path).

---

## When to use

| Scenario | Production action |
|----------|-------------------|
| Suspected duplicate fills | Stop worker + reconciliation + incident |
| Reconciliation failure | Stop worker + incident S2 |
| Deploy uncertainty | Stop worker before deploy; verify after |
| Research halt | Stop worker |

---

## Related

- [Worker safe stop](worker-safe-stop.md)
- [Reconciliation daily](reconciliation-daily.md)
- [`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md) — env defaults
- Risk R-013
