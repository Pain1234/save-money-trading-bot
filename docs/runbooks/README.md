# Runbooks

Operational procedures for paper trading stack. **Stubs marked TODO** until verified in target environment.

Only commands evidenced in repository docs are listed verbatim. Do not invent production secrets or URLs.

---

## Index

| Runbook | Status | Reference |
|---------|--------|-----------|
| Paper worker start | Partial | Below |
| Read-only API start | Partial | Below |
| Dashboard start | Partial | Below |
| Pre-deploy migrations | Documented | Below |
| Deployment verify | TODO | `docs/railway-paper-trading-dashboard-v1.md` |
| Backup create | TODO | P2 issue |
| Restore | TODO | P2 issue |
| Reconciliation check | TODO | P2 issue |
| Worker safe stop | TODO | P2 issue |
| Kill switch | Partial | API control + spec |
| Quarantine bad data | TODO | P3 issue |
| Incident response | Partial | `docs/incidents/README.md` |

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

**TODO runbook sections:** health check URLs, expected readiness timeline, log markers for READY.

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

**TODO:** local dev start command from `package.json` if different from prod — document without changing prod commands.

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

## Kill switch (V1 FREEZE)

**Intent:** Stop new entries; document current behavior in `docs/risk-specification.md`.

**TODO runbook:** exact API endpoint and auth steps from `services/paper_trading/api.py` — verify before ops use.

---

## Reconciliation check

**TODO:** Daily procedure comparing DB positions/wallet vs expected paper model; funding/mark checks for soak (P6).

---

## Backup and restore

**TODO:** Railway Postgres backup schedule, restore test steps, RPO/RTO targets (P2).

---

## Worker safe stop

**TODO:** Graceful shutdown order (worker vs API), advisory lock release verification (P2).

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
