# Railway Paper Trading Dashboard V1

This document describes the four-service Railway deployment for the approved
Paper Trading Orchestrator V1 and the public read-only dashboard at
`bot.save-money.xyz`.

## Architecture

| Service | Railway name | Public | Role |
|---------|--------------|--------|------|
| PostgreSQL | `paper-trading-postgres` | No | Persistent state |
| Worker | `paper-trading-worker` | No | Single production runner |
| API | `paper-trading-api` | No | Read-only FastAPI monitoring |
| Dashboard | `paper-trading-dashboard` | Yes | Authenticated Next.js UI |

Only `paper-trading-dashboard` receives public networking and the custom domain.
Worker, API, and PostgreSQL stay on the Railway private network.

```
Browser ──HTTPS──> paper-trading-dashboard (bot.save-money.xyz)
                         │ server-side fetch
                         └──PRIVATE_PAPER_API_URL──> paper-trading-api
                                                         └──PostgreSQL
paper-trading-worker ──────────────────────────────────> PostgreSQL
```

The browser never receives `PAPER_TRADING_DATABASE_URL`, `PRIVATE_PAPER_API_URL`,
`SESSION_SECRET`, or password material.

## Repository layout

| Path | Purpose |
|------|---------|
| `deploy/Dockerfile.paper-python` | Worker + API image (Python 3.12) |
| `deploy/Dockerfile.dashboard` | Dashboard image (Node 22 LTS) |
| `deploy/scripts/start-worker.sh` | Migrate, verify, run worker |
| `deploy/scripts/start-api.sh` | Run read-only API |
| `deploy/scripts/pre-deploy-migrate.sh` | Worker pre-deploy migrations |
| `deploy/railway/*.toml` | Railway config-as-code per service |
| `services/paper_trading/readonly_api.py` | Read-only GET API |
| `services/paper_trading/api_runner.py` | Standalone API entrypoint |
| `scripts/generate_dashboard_password_hash.py` | Password hash helper |

## GitHub / Railway setup

1. Connect the GitHub repository to a Railway project.
2. Create four services:
   - PostgreSQL plugin → name `paper-trading-postgres`
   - Empty service from repo → `paper-trading-worker`
   - Empty service from repo → `paper-trading-api`
   - Empty service from repo → `paper-trading-dashboard`
3. For each app service, set **Root Directory** to the repository root and point
   **Railway Config File** to the matching file under `deploy/railway/`.
4. Attach the PostgreSQL plugin privately to worker and API via
   `PAPER_TRADING_DATABASE_URL=${{paper-trading-postgres.DATABASE_URL}}`.
5. Set worker **Replicas** to exactly `1`. Disable serverless sleep on worker,
   API, and dashboard. Set restart policy to **Always**.

## Start commands

### Worker (`paper-trading-worker`)

Pre-deploy:

```bash
deploy/scripts/pre-deploy-migrate.sh
```

Start:

```bash
deploy/scripts/start-worker.sh
```

Equivalent runtime:

```bash
python -m alembic upgrade head
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL
python -m paper_trading
```

### Read-only API (`paper-trading-api`)

Start:

```bash
deploy/scripts/start-api.sh
```

Equivalent:

```bash
python -m paper_trading.api_runner
```

Health check path: `/health`

### Dashboard (`paper-trading-dashboard`)

Build uses `deploy/Dockerfile.dashboard` with Next.js standalone output.

Start:

```bash
node server.js
```

Public health/login path: `/login`

## Environment variables

### Worker

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `PAPER_TRADING_DATABASE_URL` | Yes | `${{paper-trading-postgres.DATABASE_URL}}` |
| `HYPERLIQUID_NETWORK` | Yes | `testnet` |
| `PAPER_PRODUCTION_MODE` | Yes | `true` |
| `PAPER_API_ENABLED` | Yes | `false` |
| `PAPER_CONTROL_API_ENABLED` | Yes | `false` |
| `PAPER_SCHEDULER_ENABLED` | Yes | `true` |
| `PAPER_FUNDING_ENABLED` | Yes | `false` |
| `PAPER_ADVISORY_LOCK_ID` | Recommended | stable integer per environment |

Do not enable live soak variables in production.

### API

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `PAPER_TRADING_DATABASE_URL` | Yes | private PostgreSQL URL |
| `PAPER_CONTROL_API_ENABLED` | Yes | `false` |
| `PAPER_API_HOST` | Recommended | `0.0.0.0` |
| `PAPER_API_PORT` | Recommended | `8080` |
| `HYPERLIQUID_NETWORK` | Recommended | `testnet` |

No trading secrets, wallet keys, or control API keys.

### Dashboard

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `PRIVATE_PAPER_API_URL` | Yes | `http://paper-trading-api.railway.internal:8080` |
| `AUTH_USERNAME` | Yes | single dashboard user |
| `AUTH_PASSWORD_HASH` | Yes | bcrypt hash, not plaintext |
| `SESSION_SECRET` | Yes | random string, ≥ 32 chars |
| `NODE_ENV` | Yes | `production` |

Optional public URL for redirects/metadata:

| Variable | Notes |
|----------|-------|
| `DASHBOARD_PUBLIC_URL` | `https://bot.save-money.xyz` |

Never set `NEXT_PUBLIC_PRIVATE_PAPER_API_URL` or expose database URLs to the
browser bundle.

## Authentication

Generate a bcrypt hash locally:

```bash
pip install bcrypt
python scripts/generate_dashboard_password_hash.py
```

Store the output in Railway as `AUTH_PASSWORD_HASH`.

Dashboard auth properties:

- single user from `AUTH_USERNAME`
- bcrypt password verification
- HttpOnly session cookie via `iron-session`
- `Secure` in production
- `SameSite=Lax`
- 12-hour session lifetime
- login rate limit (10 attempts / minute / IP)
- logout endpoint
- `/dashboard/*` protected by middleware

## Read-only API endpoints

All routes are GET-only. Non-GET requests return `405`.

| Path | Purpose |
|------|---------|
| `/health` | Liveness |
| `/readiness` | DB-backed readiness |
| `/api/v1/status` | READY / DEGRADED / STOPPED summary |
| `/api/v1/market-data` | Worker/market-data status |
| `/api/v1/wallet` | Paper wallet |
| `/api/v1/positions` | Paginated positions |
| `/api/v1/orders` | Paginated orders |
| `/api/v1/fills` | Paginated fills |
| `/api/v1/stops` | Paginated stop history |
| `/api/v1/scheduler-runs` | Paginated scheduler runs |
| `/api/v1/events` | Paginated audit events |
| `/api/v1/equity` | Paginated equity snapshots |

No mutation, control, order, wallet-signing, or kill-switch endpoints are
exposed on the read-only API service.

## Domain `bot.save-money.xyz`

1. Open Railway → `paper-trading-dashboard` → **Settings** → **Networking**.
2. Add custom domain `bot.save-money.xyz`.
3. Railway displays the exact DNS records (typically CNAME/ALIAS and optional
   verification TXT). Copy those values into your DNS provider for
   `save-money.xyz`. Do not guess CNAME targets.
4. Wait for Railway HTTPS verification to complete.
5. Optionally redirect the default `*.up.railway.app` hostname to the custom
   domain in Railway networking settings.
6. Do **not** attach this domain to worker, API, or PostgreSQL.

## Backups

Use Railway PostgreSQL backups/snapshots for `paper-trading-postgres`. Worker
and API are stateless; recovery depends on PostgreSQL restore plus a single
worker restart.

## Logs

- Worker/API: structured Python logs to stdout (`INFO paper_trading ...`).
- Dashboard: Next.js server logs to stdout.
- Use Railway log filters per service.

## Health / readiness

- API `/health` → process up
- API `/readiness` and `/api/v1/status` → DB-backed worker readiness inference
- Dashboard `/login` → app boot check
- Worker has no public HTTP port; monitor via logs, DB heartbeat, and API status

## Rollback

1. Redeploy a known-good git SHA to worker/API/dashboard separately.
2. Do not downgrade PostgreSQL schema without a tested Alembic downgrade plan.
3. Keep exactly one worker replica during rollback.

## Incident playbook

| Symptom | Check | Action |
|---------|-------|--------|
| Dashboard login works but pages red | `PRIVATE_PAPER_API_URL`, API logs | redeploy API, verify private DNS |
| Status STOPPED | worker logs, DB heartbeat | restart worker, inspect advisory lock |
| Stale heartbeat warning | worker running? DB reachable? | restart worker, check Hyperliquid connectivity |
| Migration failure on deploy | pre-deploy logs | fix schema manually, rerun `alembic upgrade head` |
| Two workers accidentally deployed | Railway replicas | scale worker back to 1 |

## Known limitations

- Dashboard shows DB-backed monitoring only; no direct Hyperliquid websocket in
  the browser or API container.
- Read-only API infers market-data readiness from worker heartbeat freshness.
- Single-user dashboard auth; no RBAC.
- No real order execution, wallet signing, or funding in V1 scope.

## Real execution excluded

Production worker runs with:

- Hyperliquid **testnet public market data only**
- `PAPER_PRODUCTION_MODE=true`
- `PAPER_CONTROL_API_ENABLED=false`
- `PAPER_API_ENABLED=false` on the worker
- no wallet or signing configuration

The public dashboard is monitoring-only.
