# Backup and Restore Runbook (P2 / Issue #11)

PostgreSQL backup strategy and restore verification for paper trading on Railway.

**Owner:** solo maintainer
**RPO target:** 24 hours — requires Railway **daily backup schedule** (not merely “backups enabled”)
**RTO target:** 4 hours (manual restore + worker restart)
**Last verified:** *not yet executed* — restore drill pending (Issue #11 open)

---

## Scope

| Component | Stateful? | Backup method |
|-----------|-----------|---------------|
| PostgreSQL (`paper-trading-postgres`) | **Yes** | Railway scheduled backups |
| Worker | No | Redeploy from git |
| Readonly API | No | Redeploy from git |
| Dashboard | No | Redeploy from git |

Worker and API recovery = PostgreSQL restore + single worker restart.
See [`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md) § Backups.

---

## Backup — Railway production

1. Open Railway project → PostgreSQL service (`paper-trading-postgres`).
2. Enable backups and configure a **daily backup schedule** (Railway documents 24h RPO only
   when daily scheduled backups are active — enabling backups without a schedule is insufficient).
3. Record latest backup timestamp weekly in personal ops log.
4. Before schema migrations: note backup age; prefer backup < 24h old.

**No application-level backup script** — rely on Railway Postgres service backups.

Reference: [Railway PostgreSQL backups](https://docs.railway.com/guides/postgresql#backups)

---

## Restore — Railway (non-prod or disaster recovery)

**Warning:** Restore overwrites target database. Use a **non-prod clone** for drills.

### Procedure

1. **Stop worker** — scale `paper-trading-worker` to 0 or disable deploy to prevent writes.
2. Railway → PostgreSQL → **Restore** from snapshot (select point-in-time or latest).
   - For drill: restore to a **new** Postgres service or Railway environment clone.
3. Update `PAPER_TRADING_DATABASE_URL` on worker + API if connection string changed.
4. Run schema verification:

   ```bash
   python scripts/verify_pg_schema.py
   ```

5. Start worker (single replica):

   ```bash
   deploy/scripts/pre-deploy-migrate.sh
   deploy/scripts/start-worker.sh
   ```

6. Verify:

   ```bash
   curl -s "$PRIVATE_PAPER_API_URL/health"
   curl -s "$PRIVATE_PAPER_API_URL/readiness" | jq '.runtime_readiness, .migration_at_head'
   curl -s "$PRIVATE_PAPER_API_URL/api/v1/wallet" | jq '.cash'
   ```

7. Run [daily reconciliation](reconciliation-daily.md) Step 2 (`python scripts/reconcile_accounting.py`).

### Rollback

If restore wrong snapshot: repeat restore with earlier backup. Do not run two workers.

---

## Local restore drill (optional — not yet executed)

Validates procedure mechanics without touching Railway production. Requires Docker.

### Setup

```powershell
docker compose -f docker/docker-compose.paper-test.yml up -d
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
python -m alembic upgrade head
```

### Create data + dump

```powershell
python -m pytest tests/paper_trading/e2e/test_full_trade_lifecycle.py::test_full_btc_trade_lifecycle -m postgres -q
$cid = docker compose -f docker/docker-compose.paper-test.yml ps -q postgres
docker exec $cid pg_dump -U postgres -d paper_trading_test -Fc -f /tmp/paper_backup.dump
docker cp "${cid}:/tmp/paper_backup.dump" ./paper_backup.dump
```

### Simulate disaster + restore

```powershell
docker compose -f docker/docker-compose.paper-test.yml down -v
docker compose -f docker/docker-compose.paper-test.yml up -d
$cid = docker compose -f docker/docker-compose.paper-test.yml ps -q postgres
docker cp ./paper_backup.dump "${cid}:/tmp/paper_backup.dump"
docker exec $cid pg_restore -U postgres -d paper_trading_test --clean --if-exists /tmp/paper_backup.dump
python scripts/verify_pg_schema.py
python scripts/reconcile_accounting.py
```

**Status:** Procedure documented; **drill not executed** (Docker unavailable on baseline host 2026-07-14).
After successful local or Railway non-prod drill, update the record below and close R-009.

### Restore drill record

| Field | Value |
|-------|-------|
| Date | *Pending* |
| Environment | local docker **or** railway-paper clone |
| Snapshot / dump used | |
| `verify_pg_schema.py` | pass/fail |
| `reconcile_accounting.py` | pass/fail |
| Operator | |

When completed, update this table and set R-009 to `closed` in [`docs/RISK_REGISTER.md`](../RISK_REGISTER.md).

---

## Related

- [Worker restart](worker-restart.md)
- [Deployment verify](deployment-verify.md)
- Risk R-009
