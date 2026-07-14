# Runbooks

Operational procedures for paper trading stack.

Only commands evidenced in repository docs are listed verbatim. Do not invent production secrets or URLs.

**Operations docs:** [`docs/operations/metrics.md`](../operations/metrics.md),
[`docs/operations/idempotency-audit.md`](../operations/idempotency-audit.md)

---

## Index

| Runbook | Status | Reference |
|---------|--------|-----------|
| Paper worker start | Complete | [Below](#paper-worker-start-production-path) |
| Read-only API start | Complete | [Below](#read-only-api-start) |
| Dashboard start | Complete | [Below](#dashboard-start) |
| Pre-deploy migrations | Complete | [Below](#migrations-local-dev) |
| Deployment verify | Complete | [deployment-verify.md](deployment-verify.md) |
| Backup and restore | TODO - Issue #11 (draft PR; do not merge until drill) | Issue #11 |
| Reconciliation check | Complete | [reconciliation-daily.md](reconciliation-daily.md) |
| Worker safe stop | Complete | [worker-safe-stop.md](worker-safe-stop.md) |
| Worker restart | Complete | [worker-restart.md](worker-restart.md) |
| Kill switch | Partial (production: worker stop; control API local/dev) | [kill-switch.md](kill-switch.md) |
| Quarantine bad data | TODO | P3 issue |
| Incident response | Complete | [`docs/incidents/README.md`](../incidents/README.md) |

---

## Paper worker start (production path)

**Environment:** Railway service `paper-trading-worker` or local with `PAPER_TRADING_DATABASE_URL`.

Pre-deploy (Railway):

```bash
deploy/scripts/pre-deploy-migrate.sh
```

Start:

```bash
deploy/scripts/start-worker.sh
```

Source: `docs/railway-paper-trading-dashboard-v1.md`, `services/paper_trading/README.md`.

**Health check:** Monitor via readonly API — `GET /api/v1/status` (`display_status`, heartbeat age).
Worker has no public HTTP port. Log markers: `worker_liveness_heartbeat`, `recover_on_startup`.

See [`docs/operations/metrics.md`](../operations/metrics.md) for readiness timeline expectations.

---

## Read-only API start

```bash
deploy/scripts/start-api.sh
```

Entrypoint: `services/paper_trading/api_runner.py` (see service README).

**Verify:** `GET /health`, `GET /readiness` on private network.

---

## Dashboard start

Built and started via `deploy/Dockerfile.dashboard` / Railway dashboard service config (`deploy/railway/paper-trading-dashboard.toml`).

Public URL (documented): `https://bot.save-money.xyz`

**Local dev:** `npm ci` then `npm run dev` with `PRIVATE_PAPER_API_URL` set (see README).

---

## Migrations (local dev)

```powershell
python -m alembic upgrade head
python scripts/verify_pg_schema.py
```

See `services/paper_trading/README.md`.

---

## Tests before deploy (developer)

```powershell
python -m pytest tests/paper_trading -m postgres -v
ruff check .
```

Full suite may require PostgreSQL and has known bulk-run isolation issues — document results in PR.

---

## Incident handling

1. Assess severity (S1–S4) — `docs/PROJECT_OPERATING_SYSTEM.md`
2. Stabilize (pause/freeze if S1/S2)
3. File incident — `docs/incidents/INCIDENT_TEMPLATE.md`
4. Fix via bug issue + regression test

---

## Contributing runbooks

Each completed runbook should include: prerequisites, steps, expected output, rollback, owner, last verified date/environment.

Open a `type:operations` issue per runbook; one PR per runbook.
