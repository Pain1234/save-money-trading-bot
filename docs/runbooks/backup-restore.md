# Backup and Restore Runbook (P2 / Issue #11)

PostgreSQL backup strategy and restore verification for paper trading on Railway.

**Owner:** solo maintainer
**RPO target:** 24 hours — daily backup schedule on the PostgreSQL volume (Railway manual or scheduled backups)
**RTO target:** 4 hours (manual restore + worker restart)
**Last verified:** 2026-07-14 — local Docker restore drill with committed trade data

---

## Scope

| Component | Stateful? | Backup method |
|-----------|-----------|---------------|
| PostgreSQL (`paper-trading-postgres`) | **Yes** | Railway volume backups and/or manual `pg_dump` |
| Worker | No | Redeploy from git |
| Readonly API | No | Redeploy from git |
| Dashboard | No | Redeploy from git |

Worker and API recovery = PostgreSQL restore + single worker restart.
See [`docs/railway-paper-trading-dashboard-v1.md`](../railway-paper-trading-dashboard-v1.md) § Backups.

**Issue #11 acceptance (split):**

| Item | Status |
|------|--------|
| Runbook + local restore drill with committed business data | Done (this doc) |
| Railway non-prod restore drill | **Open** — see account observation below |

---

## Backup — Railway production

Railway documents [manual and scheduled backups for services with volumes](https://docs.railway.com/reference/backups), including daily schedules. Hobby plans support volumes; backup UI availability depends on service configuration.

1. Open Railway project → PostgreSQL service (`paper-trading-postgres`) → **Backups**.
2. Enable backups and configure a **daily backup schedule** where the UI offers it.
3. Record latest backup timestamp weekly in personal ops log.
4. Before schema migrations: note backup age; prefer backup < 24h old.
5. Fallback: manual `pg_dump` via `PAPER_TRADING_DATABASE_URL` on a schedule.

Reference: [Railway PostgreSQL backups](https://docs.railway.com/guides/postgresql#backups),
[Railway volume reference](https://docs.railway.com/reference/volumes).

### Account observation (2026-07-14)

On project `save-money-trading-bot`, service `paper-trading-postgres`, the Backups tab displayed:
*“Backups and point-in-time recovery (PITR) are only available for customers on the Pro plan”*
and **No Backups** for the service volume. This is **account/project-specific** — not documented
here as a universal Railway rule. Re-check the UI after plan or volume changes.

---

## Restore — Railway (non-prod or disaster recovery)

**Warning:** Restore overwrites target database. Use a **non-prod clone** for drills.

When Railway volume restore is available: use PostgreSQL → **Restore** from snapshot.
Otherwise restore from a manual `pg_dump` using `pg_restore` (same verification as local drill).

### Procedure

1. **Stop worker** — scale `paper-trading-worker` to 0 or disable deploy to prevent writes.
2. Restore database (Railway snapshot **or** `pg_restore` from dump file).
3. Update `PAPER_TRADING_DATABASE_URL` on worker + API if connection string changed.
4. Run schema verification:

   ```bash
   python scripts/verify_pg_schema.py
   ```

5. Compare row counts and wallet values to a pre-backup snapshot (see local drill).
6. Start worker (single replica):

   ```bash
   deploy/scripts/pre-deploy-migrate.sh
   deploy/scripts/start-worker.sh
   ```

7. Verify API endpoints and run [daily reconciliation](reconciliation-daily.md) Step 2.

### Rollback

If restore wrong snapshot: repeat restore with earlier backup. Do not run two workers.

---

## Local restore drill

Validates restore procedure with **committed** trade lifecycle data. Requires Docker Desktop.

**Do not use postgres-marked pytest E2E for the dump:** those tests run inside a rolled-back
transaction and the session fixture downgrades schema to `base` on teardown — the dump would
contain empty seed tables only.

### Setup

```powershell
docker compose -f docker/docker-compose.paper-test.yml up -d
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
```

Wait until Postgres is **healthy**.

### Seed committed data + pre-restore snapshot

```powershell
python scripts/seed_restore_drill_data.py
```

Writes `restore_drill_snapshot.json` (gitignored). Expect `paper_fills >= 2`, `closed_positions >= 1`, wallet cash ≠ `100000`.

### Backup

```powershell
$cid = docker compose -f docker/docker-compose.paper-test.yml ps -q postgres
docker exec $cid pg_dump -U postgres -d paper_trading_test -Fc -f /tmp/paper_backup.dump
docker cp "${cid}:/tmp/paper_backup.dump" ./paper_backup.dump
```

### Simulate disaster + restore

```powershell
docker compose -f docker/docker-compose.paper-test.yml down -v
docker compose -f docker/docker-compose.paper-test.yml up -d
# wait healthy
$cid = docker compose -f docker/docker-compose.paper-test.yml ps -q postgres
docker cp ./paper_backup.dump "${cid}:/tmp/paper_backup.dump"
docker exec $cid pg_restore -U postgres -d paper_trading_test --clean --if-exists /tmp/paper_backup.dump
```

### Post-restore verification (required)

```powershell
python scripts/restore_drill_snapshot.py --compare restore_drill_snapshot.json
python scripts/verify_pg_schema.py
python scripts/reconcile_accounting.py
```

All four steps must pass. **Snapshot compare** proves business rows and wallet values survived restore.

### Restore drill record

| Field | Value |
|-------|-------|
| Date | 2026-07-14 |
| Environment | local docker (`docker/docker-compose.paper-test.yml`) |
| Snapshot / dump used | `restore_drill_snapshot.json` + `./paper_backup.dump` (~43 KB) |
| Pre/post snapshot compare | pass (`paper_fills=2`, `closed_positions=1`, wallet cash `99992.00…`) |
| `verify_pg_schema.py` | pass |
| `reconcile_accounting.py` | pass |
| Operator | Pain1234 |
| Notes | First attempt (pytest-only) invalid — empty business data. Corrected with `seed_restore_drill_data.py`. Railway UI drill still open. |

Add a second row when Railway non-prod restore is executed.

---

## Related

- [Worker restart](worker-restart.md)
- [Deployment verify](deployment-verify.md)
- `scripts/seed_restore_drill_data.py`, `scripts/restore_drill_snapshot.py`
- Risk R-009
