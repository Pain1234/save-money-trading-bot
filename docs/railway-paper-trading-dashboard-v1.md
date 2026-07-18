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
| `deploy/railpack/*.railpack.json` | Railpack fallback when Dockerfile builder is not used |
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

## Railpack vs Dockerfile (monorepo)

This repository contains both `pyproject.toml` (Python worker/API) and
`package.json` (Next.js dashboard) at the repository root. If Railway builds
with **Railpack** instead of the service-specific Dockerfile, Railpack may pick
the wrong provider and fail with `No start command detected`.

**Preferred fix:** for each app service, set **Railway Config File** to the
matching TOML under `deploy/railway/`. Those files set `builder = "DOCKERFILE"`.

| Service | Config file |
|---------|-------------|
| Worker | `deploy/railway/paper-trading-worker.toml` |
| API | `deploy/railway/paper-trading-api.toml` |
| Dashboard | `deploy/railway/paper-trading-dashboard.toml` |

**Fallback (Railpack builds):** each service TOML also sets
`RAILPACK_CONFIG_FILE` to a provider-specific config:

| Service | Railpack config | Provider |
|---------|-----------------|----------|
| Dashboard | `deploy/railpack/dashboard.railpack.json` | `node` |
| Worker | `deploy/railpack/worker.railpack.json` | `python` |
| API | `deploy/railpack/api.railpack.json` | `python` |

If Railway still auto-detects Python for the dashboard, add a service variable
`RAILPACK_CONFIG_FILE=deploy/railpack/dashboard.railpack.json` and enable
**Available during build** in the Railway UI.

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

### Research Lab (API, Issue #270)

The API image includes `examples/research/local_lab/`. `start-api.sh` sets
`RESEARCH_REPO_ROOT` / `RESEARCH_ARTIFACTS_ROOT` to `/app` and points
`RESEARCH_DATASET_CATALOG_PATH` at the shipped catalog when unset. Registry
artifacts under `/app/artifacts/research` are ephemeral across redeploys unless
a volume is attached later.

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
| `/api/v1/dashboard-summary` | Overview aggregate (status + wallet + open positions) |
| `/api/v1/market-data` | Worker/market-data status |
| `/api/v1/wallet` | Paper wallet |
| `/api/v1/positions` | Paginated positions (`open_only=true` or `status=OPEN\|CLOSING\|CLOSED`) |
| `/api/v1/orders` | Paginated orders |
| `/api/v1/fills` | Paginated fills |
| `/api/v1/stops` | Paginated stop history |
| `/api/v1/scheduler-runs` | Paginated scheduler runs |
| `/api/v1/events` | Paginated audit events |
| `/api/v1/equity` | Paginated equity snapshots |

No mutation, control, order, wallet-signing, or kill-switch endpoints are
exposed on the read-only API service.

**Deploy:** `deploy/Dockerfile.dashboard`, `deploy/railway/paper-trading-dashboard.toml`

---

## Dashboard maturity levels

Honest classification of dashboard readiness. **Planning and acceptance criteria** — not claims of completed optimization.

### Current

- Route-level `loading.tsx` skeletons verified in CI (`tests/deploy/test_dashboard_bundle.py`)

- Locally usable Next.js dashboard with login
- Real paper-trading PostgreSQL data displayable (no mock requirement in production path)
- Wallet, PnL, positions, fills, and equity visible
- Read-only — no trading mutations via dashboard or public API
- Subjectively high load times; not production-accepted as performant monitoring

### After P2.5 acceptance

- Production-accepted paper monitoring dashboard on Railway
- Measurable performance against documented budgets
- Visible loading states on all relevant routes
- Instrumented API and DB timing (server, API, SQL separable)
- Documented error and stale-data states (API down, stale heartbeat, reconciliation errors)

### After P4/P5

- Research and experiment evaluation views
- Benchmark and strategy comparison surfaces tied to experiment registry

### After P6

- Reliable 90-day paper observation data
- Paper-to-market deviation tracking
- Long-horizon operational metrics in dashboard

### P8 (future)

- Monitoring for a **separate** micro-live system
- Still no uncontrolled trading control via dashboard

See `ROADMAP.md` § P2.5 for exit criteria and performance budgets.

---

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

Use Railway PostgreSQL volume backups/snapshots for `paper-trading-postgres` when enabled in
the service Backups tab (manual and scheduled backups per
[Railway backups reference](https://docs.railway.com/reference/backups)). Fallback: manual
`pg_dump` — see [`docs/runbooks/backup-restore.md`](runbooks/backup-restore.md).

Worker and API are stateless; recovery depends on PostgreSQL restore plus a single worker restart.

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
| Build fails: `Detected Python` / `No start command` | builder + config file | link `deploy/railway/*.toml` or set `RAILPACK_CONFIG_FILE` |

## Design dashboard data mapping (#238)

`/dashboard` uses the existing Save-Money-Bot design (Navbar, Sidebar, KPIs,
chart, tables, footer). It is **read-only**.

| UI area | Data source | Notes |
|---------|-------------|--------|
| KPI Bot Status / Cash / Realized PnL / open count | `GET /api/v1/dashboard-summary` only (core path) | Preserves Issue #98 summary-first latency |
| Equity chart | `GET /api/v1/equity` (Suspense) | Chronological; empty/error states |
| Open positions table | `GET /api/v1/positions?open_only=true` (Suspense) | Side = LONG (V1); mark/TP/risk = unavailable |
| Letzte Fills | `GET /api/v1/fills` (Suspense) | No R-multiple |
| Status cards | Summary + scheduler/events (Suspense) | Readiness, scheduler, incidents |
| Win Rate / Profit Factor KPIs | — | Shown as “Nicht verfügbar” |
| Bot start/pause/stop, risk/filter controls | — | Disabled + read-only banner |

Empty, error, and stale-heartbeat states are section-local where possible; a
summary failure shows the overview error panel without blanking auth chrome.

Detail routes under `/dashboard/*` remain for diagnosis (same design shell).

## Known limitations

- Dashboard shows DB-backed monitoring only; no direct Hyperliquid websocket in
  the browser or API container.
- Read-only API infers market-data readiness from worker heartbeat freshness.
- Single-user dashboard auth; no RBAC.
- No real order execution, wallet signing, or funding in V1 scope.
- No mark price, take-profit, win rate, profit factor, or R-multiple from the API.
- V1 positions are LONG-only; the UI does not claim Short support.

## Real execution excluded

Production worker runs with:

- Hyperliquid **testnet public market data only**
- `PAPER_PRODUCTION_MODE=true`
- `PAPER_CONTROL_API_ENABLED=false`
- `PAPER_API_ENABLED=false` on the worker
- no wallet or signing configuration

The public dashboard is monitoring-only.
