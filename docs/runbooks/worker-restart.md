# Worker Restart Runbook (P2 / Issue #14)

Verify worker recovery after process termination without duplicate intents or fills.

**Owner:** solo maintainer
**Last verified:** 2026-07-14 (automated CI evidence + procedure documented)
**Environment:** Railway `paper-trading-worker` (production paper); local docker optional

---

## Prerequisites

- Exactly **one** worker replica (advisory lock assumes single holder).
- Readonly API reachable on private network.
- [`docs/operations/idempotency-audit.md`](../operations/idempotency-audit.md) reviewed.

---

## Automated evidence (CI)

The following tests run on every PR in CI job `postgres`:

```bash
python -m pytest tests/paper_trading/e2e/test_restart_lifecycle.py -m postgres -v
python -m pytest tests/paper_trading/failure/test_crash_boundaries.py -m postgres -v
python -m pytest tests/paper_trading/replay/test_replay_idempotency.py -m postgres -v
```

Key assertions:

- Orphan `RUNNING` scheduler rows cleaned on startup recovery.
- Retry after simulated crash does not duplicate intents or fills.
- Double fill invocation produces single fill row.

This satisfies Issue #14 acceptance criteria for **automated** verification.

---

## Production restart procedure (Railway)

Use after deploy, crash, or intentional recycle.

### 1. Pre-restart snapshot

Record baseline counts via readonly API (private URL):

```bash
curl -s "$PRIVATE_PAPER_API_URL/api/v1/status" | jq '.runtime.status, .heartbeat_age_seconds'
curl -s "$PRIVATE_PAPER_API_URL/api/v1/fills?limit=1" | jq '.items | length'
curl -s "$PRIVATE_PAPER_API_URL/api/v1/scheduler-runs?limit=5" | jq '.items[].status'
```

Note: `intent` count is not exposed on readonly API; use fill count and open positions
as proxy, or query DB read-only if needed.

### 2. Stop worker

In Railway dashboard → `paper-trading-worker` → **Restart** (or scale to 0 briefly).

**Do not** run two worker instances simultaneously.

Expected: heartbeat age grows; `display_status` → `DEGRADED` then `STOPPED`.

### 3. Start worker

Redeploy same commit or click **Restart**. Worker runs:

1. `pre-deploy-migrate.sh` (if configured in deploy hook)
2. `start-worker.sh` → `recover_on_startup` → scheduler loop

### 4. Post-restart verification

Within 5 minutes:

| Check | Expected |
|-------|----------|
| `GET /api/v1/status` → `display_status` | `READY` |
| `heartbeat_age_seconds` | < 300 |
| `GET /readiness` → `runtime_readiness` | `true` |
| No duplicate fills for same `deterministic_fill_key` | Query or API spot-check |
| Scheduler runs | No stuck `RUNNING` rows older than one cycle |

Worker logs should show:

```text
recover_on_startup ... final_status=READY
worker_liveness_heartbeat ... database_fingerprint=...
```

### 5. Rollback

If recovery fails (`runtime.status == FAILED`):

1. Do **not** start second worker.
2. Check logs for `ConsistencyIssue` fatal codes.
3. Invoke manual recovery via control API if configured: `POST /control/recover` with `X-API-Key`.
4. If unrecoverable, pause entries: [kill-switch](kill-switch.md) or `POST /control/pause`.
5. File S2 incident if economic state suspect.

---

## Local verification (optional)

With Docker Postgres:

```powershell
docker compose -f docker/docker-compose.paper-test.yml up -d
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
python -m alembic upgrade head
python -m pytest tests/paper_trading/e2e/test_restart_lifecycle.py -m postgres -v
```

---

## Related

- [Worker safe stop](worker-safe-stop.md)
- [Deployment verify](deployment-verify.md)
- Risk R-006, R-008 in [`docs/RISK_REGISTER.md`](../RISK_REGISTER.md)
