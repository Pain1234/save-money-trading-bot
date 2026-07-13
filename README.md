# SAVE-MONEY BOT — Trading System

Research and operations repository for trend Strategy V1, paper trading, backtesting, and the monitoring dashboard.

**Governance source of truth:** GitHub (issues, milestones, pull requests). Chat is the workbench; GitHub is the project memory.

## Quick start

### Dashboard (UI)

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The dashboard currently uses mock data for local UI development.

### Paper trading stack

See `services/paper_trading/README.md` and `deploy/scripts/` for worker/API start paths. PostgreSQL is required for the production-shaped paper path.

### Tests

```bash
python -m pytest tests/ -v
python -m pytest tests/paper_trading -m postgres -v
```

See `AGENTS.md` for lint, types, and migration commands.

## Governance

Before starting work, read:

1. `AGENTS.md` — agent and contributor rules
2. `ROADMAP.md` — active phase (P0–P9) and exit criteria
3. The **linked GitHub issue** for your branch/PR

Workflow: **one issue → one branch → one PR**. Use the PR template and `docs/DEFINITION_OF_DONE.md`.

Initialize or refresh GitHub labels, milestones, and seed issues:

```bash
python scripts/github_project_setup.py --dry-run
python scripts/github_project_setup.py --apply
```

Sequential idempotency is covered by automated tests. Official apply runs are
serialized through GitHub Actions concurrency (`.github/workflows/github-governance-setup.yml`)
and use `--skip-project`. Uncoordinated parallel local apply processes are not
claimed to be fully atomic.

The official GitHub Actions apply path intentionally uses `--skip-project`.
The repository-scoped `GITHUB_TOKEN` manages labels, milestones and issues only.
GitHub Projects v2 setup requires a separately authorized token or manual setup.

Duplicate repair is hard-restricted to `Pain1234/save-money-trading-bot`.
Before mutation, repository, issue numbers and expected titles are verified.
Repair fails closed when identity cannot be proven.

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
| `docs/strategy-specification.md` | Strategy V1 behavior (frozen) |
| `docs/risk-specification.md` | Risk limits (frozen) |
| `docs/strategy-v1-parameter-inventory.md` | Published parameter defaults |
| `docs/ARCHITECTURE.md` | System architecture (verified entrypoints) |
| `docs/DEFINITION_OF_DONE.md` | Merge checklist + review policy |
| `docs/RISK_REGISTER.md` | Risk catalog (R-001–R-005 linked to issues) |
| `docs/DECISION_LOG.md` | ADR-style decisions |
