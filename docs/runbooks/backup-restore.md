# Backup and Restore Runbook (P2 / Issue #11)

PostgreSQL backup strategy and restore verification for paper trading on Railway.

**Owner:** solo maintainer
**RPO target:** 24 hours — requires Railway **daily backup schedule** on **Pro plan** (not available on Hobby)
**RTO target:** 4 hours (manual restore + worker restart)
**Last verified:** 2026-07-14 — local Docker restore drill passed

---

## Scope

| Component | Stateful? | Backup method |
|-----------|-----------|---------------|
| PostgreSQL (`paper-trading-postgres`) | **Yes** | Railway Pro scheduled backups **or** manual `pg_dump` |
| Worker | No | Redeploy from git |
| Readonly API | No | Redeploy from git |
| Dashboard | No | Redeploy from git |

Worker and API recovery = PostgreSQL restore + single worker restart.
See [`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md) § Backups.

---

## Backup — Railway production

1. Open Railway project → PostgreSQL service (`paper-trading-postgres`).
2. **Pro plan required:** enable backups and configure a **daily backup schedule** (Railway
   documents 24h RPO only when daily scheduled backups are active).
3. On Hobby/free tier: managed backups are **not available** — use manual `pg_dump` via
   `PAPER_TRADING_DATABASE_URL` on a schedule, or upgrade to Pro.
4. Record latest backup timestamp weekly in personal ops log.
5. Before schema migrations: note backup age; prefer backup < 24h old.

Reference: [Railway PostgreSQL backups](https://docs.railway.com/guides/postgresql#backups)

---

## Restore — Railway (non-prod or disaster recovery)

**Warning:** Restore overwrites target database. Use a **non-prod clone** for drills.

**Requires Railway Pro** for UI snapshot restore. Without Pro, restore from a manual `pg_dump`
file using `pg_restore` (same verification steps as local drill below).

### Procedure

1. **Stop worker** — scale `paper-trading-worker` to 0 or disable deploy to prevent writes.
2. Railway → PostgreSQL → **Restore** from snapshot (Pro plan only).
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

## Local restore drill

Validates restore procedure mechanics without touching Railway production. Requires Docker Desktop.

**Status:** **Executed 2026-07-14** — schema verification and reconciliation passed after
`pg_restore`. Railway managed backups not tested (Pro plan not enabled).

### Setup

```powershell
docker compose -f docker/docker-compose.paper-test.yml up -d
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
python -m alembic upgrade head
```

### Create data + dump

```powershell
python -m pytest "tests/paper_trading/e2e/test_full_trade_lifecycle.py::test_full_btc_trade_lifecycle" -m postgres -q

# Required: pytest session teardown runs alembic downgrade — re-apply schema before dump.
python -m alembic upgrade head

$cid = docker compose -f docker/docker-compose.paper-test.yml ps -q postgres
docker exec $cid pg_dump -U postgres -d paper_trading_test -Fc -f /tmp/paper_backup.dump
docker cp "${cid}:/tmp/paper_backup.dump" ./paper_backup.dump
```

Expect dump size well above empty (~40 KB+ with schema); ~1.7 KB indicates dump ran after
pytest teardown removed tables.

### Simulate disaster + restore

Wait for Postgres **healthy** after `up -d`, then:

```powershell
docker compose -f docker/docker-compose.paper-test.yml down -v
docker compose -f docker/docker-compose.paper-test.yml up -d
$cid = docker compose -f docker/docker-compose.paper-test.yml ps -q postgres
docker cp ./paper_backup.dump "${cid}:/tmp/paper_backup.dump"
docker exec $cid pg_restore -U postgres -d paper_trading_test --clean --if-exists /tmp/paper_backup.dump
python scripts/verify_pg_schema.py
python scripts/reconcile_accounting.py
```

### Restore drill record

| Field | Value |
|-------|-------|
| Date | 2026-07-14 |
| Environment | local docker (`docker/docker-compose.paper-test.yml`) |
| Snapshot / dump used | `./paper_backup.dump` (~39 KB, custom format) |
| `verify_pg_schema.py` | pass |
| `reconcile_accounting.py` | pass |
| Operator | Pain1234 |

When Railway Pro backups are enabled, add a second row for production or non-prod clone restore.

---

## Related

- [Worker restart](worker-restart.md)
- [Deployment verify](deployment-verify.md)
- Risk R-009
