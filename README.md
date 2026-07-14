# SAVE-MONEY BOT — Trading System

Research and operations repository for trend Strategy V1, paper trading, backtesting, and the monitoring dashboard.

**Governance source of truth:** GitHub (issues, milestones, pull requests). Chat is the workbench; GitHub is the project memory.

**Current workstream:** P1 — Reproducible Baseline Release (`ROADMAP.md`). Baseline reference: `docs/baseline-paper-v1.md`. CI: `.github/workflows/ci.yml`.

## Quick start

### Paper trading stack (production-shaped)

PostgreSQL is required. Production start paths live under `deploy/scripts/`:

```bash
pip install -e ".[api]"
export PAPER_TRADING_DATABASE_URL="postgresql+psycopg://…"
deploy/scripts/start-worker.sh    # migrate, verify, run worker
deploy/scripts/start-api.sh       # read-only API on :8080
```

Local PostgreSQL for tests: `docker/docker-compose.paper-test.yml` (port 5433) or
see `services/paper_trading/README.md`.

Full baseline: **`docs/baseline-paper-v1.md`** (env vars, versions, tests, tag criteria).

### Dashboard (UI)

**Local development** (`next dev`) — server routes under `/dashboard` require env vars
(including `PRIVATE_PAPER_API_URL`; see `src/lib/paper-api/client.ts`):

```bash
npm ci
# .env.local — SESSION_SECRET, PRIVATE_PAPER_API_URL, AUTH_USERNAME, AUTH_PASSWORD_HASH
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Start the read-only paper API
locally or point `PRIVATE_PAPER_API_URL` at a running instance.

**Local production build** (`next start`):

```bash
npm ci
# SESSION_SECRET, PRIVATE_PAPER_API_URL, AUTH_USERNAME, AUTH_PASSWORD_HASH — see .env.example
npm run build
npm start
```

**Railway / Docker** uses standalone output (`node server.js` per
`deploy/Dockerfile.dashboard`), not `npm start`.

`npm ci` is required before `npm run build` or `npm run dev` on a fresh clone.
Issue #58: build test failure was missing `npm ci`, not a dashboard source defect.

### Tests

```bash
python -m pytest tests/ -v
python -m pytest tests/paper_trading -m postgres -v   # requires PostgreSQL
ruff check .
```

See `docs/baseline-paper-v1.md` for markers, CI jobs, and recorded baseline results.

## Governance

Before starting work, read:

1. `AGENTS.md` — agent and contributor rules
2. `ROADMAP.md` — active phase (P0–P9) and exit criteria
3. The **linked GitHub issue** for your branch/PR

Workflow: **one issue → one branch → one PR**. Use the PR template and `docs/DEFINITION_OF_DONE.md`.

Initialize or refresh GitHub labels, milestones, and seed issues:

```bash
python scripts/github_project_setup.py --dry-run --skip-project
python scripts/github_project_setup.py --apply --skip-project
```

See `docs/PROJECT_OPERATING_SYSTEM.md` for the full operating model.

## Repository layout

```
services/
├── strategy_engine/   # Strategy V1 (frozen spec)
├── risk_engine/       # Risk V1 (frozen spec)
├── backtester/        # Backtest execution layer
├── market_data/       # Hyperliquid market data
└── paper_trading/     # Paper orchestrator (PostgreSQL)
src/                   # Next.js dashboard
docs/                  # Specs, runbooks, decision log
deploy/                # Railway/Docker production paths
```

## Key specs

| Document | Purpose |
|----------|---------|
| `docs/baseline-paper-v1.md` | P1 reproducible baseline (start, versions, tests) |
| `docs/default-branch-migration-plan.md` | Default branch migration record (`main`, #64) |
| `docs/branch-protection.md` | Required CI checks on `main` (#65) |
| `docs/strategy-specification.md` | Strategy V1 behavior (frozen) |
| `docs/risk-specification.md` | Risk limits (frozen) |
| `docs/strategy-v1-parameter-inventory.md` | Published parameter defaults |
| `docs/ARCHITECTURE.md` | System architecture (verified entrypoints) |
| `docs/DEFINITION_OF_DONE.md` | Merge checklist + review policy |
| `docs/RISK_REGISTER.md` | Risk catalog (R-001–R-005 linked to issues) |
| `docs/DECISION_LOG.md` | ADR-style decisions |
| `docs/railway-paper-trading-dashboard-v1.md` | Railway four-service deployment |
