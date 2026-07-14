# System Architecture

Evidence-based map of the **save-money-trading-bot** repository as implemented today. Gaps are labeled **Current Gap** — not aspirational architecture.

Related specs: `docs/product-specification.md`, `docs/strategy-specification.md`, `docs/risk-specification.md`, `docs/paper-trading-orchestrator-v1.md`, `docs/railway-paper-trading-dashboard-v1.md`.

---

## High-level diagram

```
                    ┌─────────────────────────────────────────┐
                    │           Hyperliquid (public)           │
                    │     REST / WebSocket market data         │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         services/market_data             │
                    │  ingest, candles, reconnect, backfill    │
                    └──────────────────┬──────────────────────┘
                                       │ events / candles
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
         ▼                             ▼                             ▼
┌─────────────────┐        ┌─────────────────────┐        ┌─────────────────┐
│ strategy_engine │        │  paper_trading       │        │   backtester    │
│ signals / rules │◄──────►│  orchestrator V1     │        │  historical sim │
└────────┬────────┘        └──────────┬───────────┘        └────────┬────────┘
         │                              │                              │
         ▼                              ▼                              ▼
┌─────────────────┐        ┌─────────────────────┐        ┌─────────────────┐
│  risk_engine    │        │  PostgreSQL          │        │  in-memory /    │
│  limits, sizing │        │  (paper state)       │        │  file datasets  │
└─────────────────┘        └──────────┬───────────┘        └─────────────────┘
                                      │
                         ┌────────────┴────────────┐
                         │                         │
                         ▼                         ▼
              ┌──────────────────┐      ┌──────────────────────┐
              │ readonly_api     │      │  Next.js dashboard    │
              │ (FastAPI GET)    │◄─────│  bot.save-money.xyz   │
              └──────────────────┘      └──────────────────────┘

trading_constraints — exchange meta, symbol constraints (shared)
```

**Live execution:** **Current Gap** — not implemented. Paper orchestrator explicitly excludes Hyperliquid private API, wallet signing, and real orders (`services/paper_trading/README.md`).

---

## Production entrypoints

Verified against `deploy/scripts/`, `deploy/railway/`, and Python module entrypoints (2026-07-13).

| Role | How it starts (production) | Command / module | Required env (minimum) |
|------|----------------------------|------------------|-------------------------|
| **Paper worker** | `deploy/scripts/start-worker.sh` | `python -m paper_trading` → `paper_trading.runner:main` | `PAPER_TRADING_DATABASE_URL` |
| **Read-only API** | `deploy/scripts/start-api.sh` | `python -m paper_trading.api_runner` → FastAPI via uvicorn | `PAPER_TRADING_DATABASE_URL`; `PAPER_CONTROL_API_ENABLED=false` |
| **DB migrate** | worker start or `deploy/scripts/pre-deploy-migrate.sh` | `python -m alembic upgrade head` | `PAPER_TRADING_DATABASE_URL` |
| **Pre-start verify** | worker start (after migrate) | `python scripts/verify_paper_state.py` | `PAPER_TRADING_DATABASE_URL` |
| **Dashboard** | Railway `paper-trading-dashboard.toml` | `npm run build` → `node server.js` | `PAPER_API_URL`, session secret (see deploy docs) |

**Not production-deployed (research / ops tooling):**

| Role | Command | Notes |
|------|---------|-------|
| Backtester | `pytest tests/backtester` or import `backtester.engine` | No Railway service; library + tests |
| Strategy / risk engines | imported by paper + backtester | No standalone process |
| Market data runtime | embedded in paper worker | `HyperliquidMarketDataRuntime` via `PaperTradingApplication` — no separate `__main__` |
| Schema check | `python scripts/verify_pg_schema.py` | Manual/CI helper |
| Soak runner | `python scripts/run_paper_soak.py` | Long-running test harness |
| Governance setup | `python scripts/github_project_setup.py --apply` | GitHub labels/milestones/issues |

**Local development (non-production):**

| Role | Command |
|------|---------|
| Dashboard UI | `npm run dev` (mock data) |
| Full test suite | `python -m pytest tests/ -v` |
| Postgres integration | `python -m pytest tests/paper_trading -m postgres -v` |

---

## Module responsibilities

### Data ingestion — `services/market_data/`

| Responsibility | Details |
|----------------|---------|
| Connect to Hyperliquid | WebSocket + REST (`network/`, `runtime.py`) |
| Candle aggregation | Multiple intervals; ISO weekly derived from daily (not native `1w` subscription) |
| Reconnect / degraded mode | Transport reconnect; readiness interaction with paper worker |
| Backfill | `initial_backfill.py`, repository upserts |
| Persistence | PostgreSQL candle tables (shared DB with paper trading in deployment) |

**Persistent state:** Candle rows, subscription cursors, advisory locks for refresh.

**Entrypoints:** No standalone production process. Started inside the paper worker via `PaperTradingApplication._build_market_data_runtime()` (`services/paper_trading/application.py`).

**Risks:** Reconnect deadlocks (mitigated in recent fixes); gap detection not fully productized (**Current Gap** P3).

---

### Data validation — partial

| Responsibility | Details |
|----------------|---------|
| Schema verification | `scripts/verify_pg_schema.py` |
| Recovery consistency | `services/paper_trading/recovery.py` |
| Symbol constraints | `services/paper_trading/symbol_constraints.py`, `services/trading_constraints/` |

**Current Gap:** Centralized data-quality pipeline with manifests and quarantine (P3).

---

### Data storage — PostgreSQL

| Responsibility | Details |
|----------------|---------|
| Paper trading domain | Intents, orders, fills, positions, wallet, snapshots, scheduler, audit |
| Market data | Candles and related tables |
| Migrations | Alembic `001`–`009` at repository root `migrations/` |

**Production URL:** `PAPER_TRADING_DATABASE_URL` (Railway private network).

**Risks:** Single DB for paper + market data — backup/restore critical (**Current Gap** documented runbook).

---

### Research — `services/backtester/`, specs

| Responsibility | Details |
|----------------|---------|
| Historical simulation | Backtester service |
| Strategy definition | `services/strategy_engine/` |
| Specs | `docs/strategy-specification.md`, experiment templates |

**Current Gap:** Unified experiment registry and enforced pipeline (P4).

---

### Backtesting — `services/backtester/`

| Responsibility | Details |
|----------------|---------|
| Replay strategy on historical data | Parity goal with paper fill model |
| Tests | Under `tests/` |

**Dependencies:** Strategy engine, risk engine, market data fixtures.

---

### Strategies — `services/strategy_engine/`

| Responsibility | Details |
|----------------|---------|
| Trend Strategy V1 logic | Per frozen spec |
| Evaluation inputs | Candles, indicators |

**Do not change parameters** without governance issue + approval.

---

### Shared constraints — `services/trading_constraints/`

| Responsibility | Details |
|----------------|---------|
| Symbol constraint validation | `quantity_step`, `minimum_quantity`, tick size, notional floors |
| Consumers | `risk_engine`, `paper_trading.constraint_validation`, backtester |

**Entrypoints:** Library only — no production process.

---

### Portfolio — `services/paper_trading/portfolio.py`

| Responsibility | Details |
|----------------|---------|
| Idempotent portfolio snapshots | After fills/evaluation |
| Exposure tracking | Paper wallet |

---

### Risk management — `services/risk_engine/`, `docs/risk-specification.md`

| Responsibility | Details |
|----------------|---------|
| Position sizing, limits | Shared between backtest and paper paths |
| Kill switch | FREEZE mode in V1 (paper control plane) |

**Risks:** Paper model may not match live slippage/fees (P6 decay measurement).

---

### Paper execution — `services/paper_trading/`

| Responsibility | Details |
|----------------|---------|
| Lifecycle | `evaluation.py` → `lifecycle.py` → fills |
| Scheduler | `scheduler.py`, deterministic jobs |
| Runtime FSM | `runtime.py`: STARTING → RECOVERING → SYNCING → READY / DEGRADED / FAILED |
| Single runner | PostgreSQL advisory lock (`lock.py`) |
| Heartbeat / readiness | `heartbeat.py`, `readiness.py` |
| API (control) | `api.py` — read + control endpoints for ops |
| Production runner | `application.py`, `api_runner.py` |

**Production entrypoints (do not change without issue):** see [Production entrypoints](#production-entrypoints) above.

- Worker: `deploy/scripts/start-worker.sh`
- API: `deploy/scripts/start-api.sh`
- Pre-deploy migrate: `deploy/scripts/pre-deploy-migrate.sh`

**Internal phases 1–9:** Complete. Phase 10 audit/hardening gate open.

---

### Live execution

**Current Gap — not implemented.**

---

### Accounting — paper wallet and fills

| Responsibility | Details |
|----------------|---------|
| Fill chain | Entry/exit fills, `fill_kind`, wallet updates |
| Audit trail | `audit-events` API surface |

**Risks:** S1 if fill/position/wallet chain inconsistent — recovery treats as fatal (`recovery.py`).

---

### Reconciliation

| Responsibility | Details |
|----------------|---------|
| Startup recovery | Consistency checks in `recovery.py` |
| Manual wallet mismatch | Requires manual intervention |

**Current Gap:** Daily operational reconciliation runbook and automated exchange reconcile (live N/A).

---

### Monitoring — readonly API + dashboard

| Responsibility | Details |
|----------------|---------|
| Read-only API | `readonly_api.py`, `/health`, `/readiness`, `/runtime`, portfolio/positions/orders/fills |
| Dashboard | Next.js app, server-side fetch to private API |
| Observability | Database fingerprint, heartbeat timestamps, structured reconnect logs |

**Public surface:** Dashboard only (`docs/railway-paper-trading-dashboard-v1.md`).

---

### Dashboard — repository root frontend

| Responsibility | Details |
|----------------|---------|
| Authenticated UI | Session secret; no DB credentials in browser |
| Status polling | `fetchStatus()` with cache bypass where configured |

**Deploy:** `deploy/Dockerfile.dashboard`, `deploy/railway/paper-trading-dashboard.toml`

---

### Deployment — `deploy/`

| Component | Path |
|-----------|------|
| Docker images | `deploy/Dockerfile.paper-python`, `deploy/Dockerfile.dashboard` |
| Railway config | `deploy/railway/*.toml` |
| Railpack fallback | `deploy/railpack/*.railpack.json` |
| Local test compose | `docker/docker-compose.paper-test.yml` |

**CI:** `.github/workflows/ci.yml` — mandatory compile, governance tests, ruff, unit pytest, and PostgreSQL integration (#53). Path-filtered governance apply: `.github/workflows/github-governance-setup.yml` (PR #54). Dashboard build test excluded from CI (Issue #58). Branch protection pending default-branch migration (#52).

---

## Data flows (paper production path)

1. **Market data** ingests candles → PostgreSQL.
2. **Market events** bridge notifies paper **scheduler** on new closed bars.
3. **Evaluation** runs strategy at daily close boundaries.
4. **Lifecycle** creates intents; **scheduler** executes scheduled fills (paper model).
5. **Portfolio** snapshots updated; **heartbeat** and **readiness** committed cross-session.
6. **Readonly API** serves dashboard; browser never sees DB URL.

---

## System boundaries

| Inside V1 paper production | Outside / not implemented |
|----------------------------|---------------------------|
| Public market data | Private trading API |
| Simulated fills | Exchange order placement |
| Single worker + advisory lock | Multi-region active-active |
| Railway Postgres | **Current Gap:** documented DR |

---

## Known cross-cutting risks

See `docs/RISK_REGISTER.md`. Highest priority: execution/accounting integrity (S1), paper-to-live decay, full test CI gap (#53), DoD review enforcement (#5). P0 exit incomplete — see `ROADMAP.md` § P0 exit criteria.

---

## Verification log

| Date | Change | Issue |
|------|--------|-------|
| 2026-07-13 | Production entrypoints table; migrations `001`–`009`; `trading_constraints` module | #3 |
| 2026-07-14 | CI workflow `ci.yml`; branch migration plan doc (#52); baseline tag criteria met | #53, #10, #52 |

## Document maintenance

Update this file when module boundaries or production entrypoints change. Link the governing issue/PR. Do not document wished-for architecture as existing fact.
