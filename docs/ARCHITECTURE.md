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
| Dashboard UI | `npm run dev` with `PRIVATE_PAPER_API_URL` (read-only paper API; no mock finance on `/dashboard`) |
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
| Persistence | **In-process only** — `InMemoryCandleRepository` (`repository.py`); lost on worker restart |

**Persistent state:** No durable candle rows or market-data catalog today. HTTP pagination cursors in `providers/hyperliquid_historical.py` exist only for the duration of a single backfill request (in-process). The PostgreSQL advisory lock (`paper_trading/lock.py`) serializes the **entire paper worker** via `PaperTradingApplication`; it is not a market-data refresh lock and does not live under `services/market_data/`. **P3 gap:** versioned raw artifact storage and normalized catalog per storage ADR.

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
| Market data | **Not persisted today** — in-memory candles only; Alembic has no candle tables (P3) |
| Migrations | Alembic `001`–`009` at repository root `migrations/` |

**Production URL:** `PAPER_TRADING_DATABASE_URL` (Railway private network).

**Risks:** Single DB for paper + market data — backup/restore critical (**Current Gap** documented runbook).

---

### Research — `services/research/`, backtester, specs

| Responsibility | Details |
|----------------|---------|
| Historical simulation | Backtester service |
| Strategy definition | `services/strategy_engine/` |
| Experiment pipeline | Spec, runner, `ExperimentRegistry` (`registry.jsonl`), metrics/artifacts incl. `chart_data.json` (run-bound OHLCV per symbol, written at finalize from the filtered dataset bundle) |
| Read API | Mounted on readonly app: `/api/v1/research/overview`, `/experiments`, `/experiments/{id}` (+ optional metrics/equity/artifacts); `/experiments/{id}/trades`, `/experiments/{id}/chart-data?symbol=`; `/strategies`, `/strategies/{id}`, `/strategies/{id}/schema` |
| Workspace UI | `/dashboard/research` overview / list / detail (incl. **Kurs & Trades** price/trade chart on experiment detail); strategy catalog `/dashboard/research/strategies` (+ `/{id}`); Strategy Lab `/dashboard/research/experiments/new` starts `run_experiment` via job store (no cancel/promotion) |
| Write surface | POST `/api/v1/research/experiments` + `.../start` allow-listed on private dashboard API; dataset catalog only (no free client paths) |
| Strategy identity | Canonical `trend_v1` (display: Trend Strategy V1); alias `trend_strategy_v1` resolvable for historical specs; `services/research/strategy_resolver.py` is SoT — no second registry |
| Specs | `docs/strategy-specification.md`, experiment templates |

**Current Gap:** Compare/robustness UI, gate evaluator, durable multi-process queue, Cancel/Retry (see `docs/project-management/p4-research-workspace-follow-ups.md`). No second registry; no Experiment Postgres tables.

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
| Read-only API | `readonly_api.py`, `/health`, `/readiness`, `/runtime`, portfolio/positions/orders/fills; Research GET + allow-listed Research POST under `/api/v1/research/*` |
| Dashboard | Next.js app, server-side fetch to private API (Monitor + Research workspaces incl. Strategy Lab) |
| Observability | Database fingerprint, heartbeat timestamps, structured reconnect logs |

**Public surface:** Dashboard only (`docs/railway-paper-trading-dashboard-v1.md`).

---

### Dashboard — repository root frontend

| Responsibility | Details |
|----------------|---------|
| Authenticated UI | Session secret; no DB credentials in browser |
| Status polling | `fetchStatus()` with cache bypass where configured |

**Deploy:** `deploy/Dockerfile.dashboard`, `deploy/railway/paper-trading-dashboard.toml`

**Maturity:** Locally usable with real paper data; production performance acceptance is **P2.5** scope (`docs/railway-paper-trading-dashboard-v1.md` § Dashboard maturity levels). Not yet classified as production-accepted performant monitoring.

---

### Multi-asset target architecture

**Target state (P7 planning — not implemented).** ADR-014 (amended) + ADR-018:
one research and paper-trading platform; research universes are separate from
execution venues; centralized intent allocation with a single execution owner
per trading account. No automatic separate repository. Accepting these ADRs is
**architecture/planning only** — not runtime activation.

```text
Market Data
→ Universe Discovery
→ Asset Profile
→ Multi-Timeframe Context
→ Strategy Signals
→ Normalized Strategy Intents
→ Eligibility Gates
→ Opportunity Ranking
→ Correlation Clustering
→ Portfolio Allocation
→ Global Risk Engine
→ Target Position Netting
→ Single Execution Owner
→ Venue Adapter
→ Hyperliquid or later venues
```

```text
One Trading and Research Platform
├── Research Universes (Crypto, FX, Equity Indices, Commodities, Rates, Equities)
├── First execution / paper venue path (Hyperliquid core + optional HIP-3)
├── Shared Research Pipeline
├── Orthogonal metadata (asset_class × instrument_type × venue profile)
├── Asset-Specific Cost and Funding Models
├── Shared Portfolio Risk Layer (cluster budgets; ADR-018 allocator)
└── Single Execution Owner → Venue Adapter
```

**Orthogonal metadata axes** (single registry — #104; not a second registry):

| Axis | Values |
|------|--------|
| `asset_class` | `CRYPTO`, `FX`, `EQUITY`, `INDEX`, `COMMODITY`, `RATES` |
| `instrument_type` | `SPOT`, `PERPETUAL`, `FUTURE`, `CASH_EQUITY`, `SYNTHETIC_PERPETUAL` |
| Venue / execution profile | Hyperliquid core, HIP-3 market, later venues |

Example combinations: `CRYPTO+PERPETUAL`, `EQUITY+SYNTHETIC_PERPETUAL`,
`INDEX+SYNTHETIC_PERPETUAL`, `COMMODITY+FUTURE`, `COMMODITY+SYNTHETIC_PERPETUAL`,
`FX+SPOT`, `RATES+FUTURE`. HIP-3 index/commodity markets are
**synthetic perpetuals**, not futures. Legacy ADR-014 names
(`CRYPTO_24_7`, `HIP3_*`) map as venue-specific aliases.

Each profile must eventually capture at minimum:

| Dimension | Examples |
|-----------|----------|
| Venue / DEX | Hyperliquid core vs HIP-3 market (execution profile) |
| Trading calendar / timezone / sessions | 24/7 crypto vs FX 24/5 vs equity sessions |
| Symbol metadata | Tick size, lot size, quote currency, margin asset |
| Oracle / mark price source | Per-market oracle rules |
| Funding / roll costs | Interval, caps, asset-specific behavior |
| Fees / slippage | Cost model inputs |
| Available history | Minimum backtest depth |
| Minimum liquidity | Volume/spread thresholds |
| Price gaps / corporate actions | Session open, halts, dividends, reference adjustments |
| Benchmark / regime profile | Research evaluation context |
| Correlation clusters | BTC/ETH/SOL, sector/index clusters |
| Position limits | Per-asset and per-cluster caps |

**Identity scaffolding (#128–#130):** Additive `InstrumentId` plumbing may merge
before P5/P6 under ADR-018 parity and freeze-window rules. It is **not**
multi-asset activation. BTC/ETH/SOL economic behavior must remain equivalent
under golden fixtures.

**Boundaries today:** Paper worker trades crypto perpetuals only (BTC/ETH/SOL).
HIP-3 and other research universes are roadmap items (P7 planning). Live trading
for any asset class remains **P8** with human approval. Subaccounts are P8
optional isolation — not a P7 runtime deliverable. P4.9 Research Workspace UI
(#297–#303) provides design system + scorecard; P7 cross-asset views are #139.

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

1. **Market data** ingests candles → in-memory repository (PostgreSQL persistence planned in P3).
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
