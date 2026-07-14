# Worker Safe Stop Runbook (P2)

Graceful shutdown order for paper trading worker without leaving orphan scheduler state.

**Owner:** solo maintainer
**Last verified:** 2026-07-14

---

## Prerequisites

- Exactly one worker replica.
- Advisory lock held by running worker (normal steady state).

---

## Railway production (default)

Control API is **disabled** (`PAPER_CONTROL_API_ENABLED=false`). Pause via HTTP is **not available**.

1. **Optional — verify steady state** via readonly API:

   ```bash
   curl -s "$PRIVATE_PAPER_API_URL/api/v1/status" | jq '.display_status, .heartbeat_age_seconds'
   ```

2. **Wait one scheduler cycle** (~60s) so in-flight jobs can complete.

3. **Stop worker** — Railway → `paper-trading-worker` → Stop or scale to 0.

4. **Verify heartbeat stopped** — `heartbeat_age_seconds` grows; `display_status` → `DEGRADED`/`STOPPED`.

5. **After restart**, check for orphan `RUNNING` scheduler rows:

   ```bash
   curl -s "$PRIVATE_PAPER_API_URL/api/v1/scheduler-runs?limit=10" | jq '.items[] | select(.status=="RUNNING")'
   ```

   Recovery should clear orphans on startup (`recover_on_startup`).

---

## Local / dev (control API enabled)

When running worker with `PAPER_API_ENABLED=true` and `PAPER_CONTROL_API_ENABLED=true`:

```bash
curl -X POST "http://127.0.0.1:8080/control/pause" -H "X-API-Key: $PAPER_CONTROL_API_KEY"
```

Then stop the process. See [kill-switch](kill-switch.md) for env setup.

---

## Do not

- Run two worker instances simultaneously.
- Stop PostgreSQL while worker is writing (stop worker first).
- Force-kill repeatedly without reconciliation afterward.

---

## Related

- [Worker restart](worker-restart.md)
- [Kill switch](kill-switch.md)
