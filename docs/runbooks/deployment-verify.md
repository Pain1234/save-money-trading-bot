# Deployment Verify Runbook (P2)

Post-deploy checks for Railway paper trading stack.

**Owner:** solo maintainer
**Last verified:** 2026-07-14
**Reference:** [`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md)

---

## Services

| Service | Branch | Start command |
|---------|--------|---------------|
| `paper-trading-worker` | `main` | `deploy/scripts/start-worker.sh` |
| `paper-trading-api` | `main` | `deploy/scripts/start-api.sh` |
| `paper-trading-dashboard` | `main` | `node server.js` |
| PostgreSQL | managed | Railway |

Pre-deploy migration hook: `deploy/scripts/pre-deploy-migrate.sh`

---

## Verify checklist (after each deploy)

### 1. Migrations

Worker/API logs should show Alembic at head without error.

Local equivalent:

```powershell
python -m alembic upgrade head
python scripts/verify_pg_schema.py
```

### 2. API health

```bash
curl -s -o /dev/null -w "%{http_code}" "$PRIVATE_PAPER_API_URL/health"
# expect 200

curl -s "$PRIVATE_PAPER_API_URL/readiness" | jq '.runtime_readiness, .migration_at_head, .database_ready'
# expect true, true, true when worker running
```

### 3. Worker readiness

Within 5 minutes of worker start:

- `GET /api/v1/status` → `display_status: "READY"`
- `heartbeat_age_seconds` < 300
- Worker logs: `final_status=READY` or successful heartbeat events

See [`docs/operations/metrics.md`](../operations/metrics.md).

### 4. Dashboard

- Public URL loads login page (`https://bot.save-money.xyz` per deploy docs).
- Authenticated status page shows heartbeat age and readiness reasons.

Requires env: `PRIVATE_PAPER_API_URL`, `SESSION_SECRET`, auth hash vars.

### 5. Database fingerprint

Compare worker vs API startup logs for matching `database_fingerprint`.

### 6. CI parity (pre-merge)

Mandatory checks on PR to `main`: `validate`, `lint`, `test`, `test-market-data`,
`test-deploy`, `postgres`, `requirements-baseline`.

---

## Rollback

1. Redeploy previous known-good git SHA per service (worker/API/dashboard independently).
2. Do **not** downgrade PostgreSQL schema without tested Alembic downgrade.
3. Keep exactly one worker replica.
4. Run [reconciliation](reconciliation-daily.md) after rollback if worker was running during incident.

---

## Related

- [Worker restart](worker-restart.md)
- [Backup restore](backup-restore.md)
