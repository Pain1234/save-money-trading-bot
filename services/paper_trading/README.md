# Paper Trading Orchestrator (Phases 1–9)

## Scope

Phases 1–9 implement domain, PostgreSQL persistence, execution parity with the backtester, evaluation/intent/fill lifecycle, stop/close/portfolio snapshots, internal scheduler, composite readiness, deterministic recovery, FastAPI read/control plane, and Phase 9 E2E/replay/crash/soak validation.

Not implemented: Hyperliquid private API, wallet/signing, real exchange orders (Phase 10 audit gate).

**Order lifecycle V1 (AUD-P2-002 / #390):** Paper execution performs a **single full fill** per intent.
Enums/schema may mention richer states, but the following are **NOT_IMPLEMENTED** and must not be
treated as live-readiness or P8 prerequisites until a dedicated issue delivers end-to-end behavior
and tests:

- partial fills
- cancel / replace (amend) transitions
- persistent exchange-style protective stop orders (V1 uses evaluation-time stop logic, not a
  durable protective order object on the venue)

Planning issues #304/#305 (P7 intent contracts) are **not** substitutes for implementing this
lifecycle.

## Key modules

| Module | Purpose |
|--------|---------|
| `clock.py` | Injectable UTC clock |
| `evaluation.py` | Daily-close strategy evaluation |
| `lifecycle.py` | Intent creation, scheduled fills |
| `stops.py` | Trailing stops, stop triggers, close |
| `portfolio.py` | Idempotent portfolio snapshots |
| `scheduler.py` | Deterministic job runner |
| `readiness.py` | Liveness / runtime / entry readiness |
| `runtime.py` | Runtime state machine, pause, kill, startup recovery |
| `lock.py` | PostgreSQL advisory lock |
| `recovery.py` | Consistency checks, auto-repair, startup recovery |
| `market_events.py` | Market-data → scheduler event bridge |
| `scheduler_context.py` | Production scheduler context from market data |
| `symbol_constraints.py` | Hyperliquid meta / env constraints (fail-closed) |
| `application.py` | Production runner wiring and event loop |
| `controlled_market_data.py` | Scriptable market-data runtime for tests |
| `db/transaction.py` | Nested transaction/savepoint helper |
| `api.py` | FastAPI read and control endpoints |

## Local PostgreSQL test setup (Windows)

1. Install PostgreSQL 16 (e.g. `winget install PostgreSQL.PostgreSQL.16`).
2. Create local test role and database only (no production credentials):

```sql
CREATE ROLE paper_trading_test LOGIN PASSWORD '<LOCAL_TEST_PASSWORD>';
CREATE DATABASE paper_trading_test OWNER paper_trading_test;
```

3. Set session URL (do not commit password):

```powershell
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://paper_trading_test:<LOCAL_TEST_PASSWORD>@localhost:5432/paper_trading_test"
python -m alembic upgrade head
python -m pytest tests/paper_trading -m postgres -v
```

Alternative: `docker/docker-compose.paper-test.yml` on port `5433`.

## Migrations

Alembic revisions `001`–`009` (latest: `009_soak_run_identity`).

```powershell
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
python scripts/verify_pg_schema.py
```

## Recovery policy

Startup flow: `STARTING → RECOVERING → SYNCING → READY` (or `DEGRADED` / `FAILED`).

**Auto-repairable:** orphan `RUNNING` scheduler runs, stale heartbeat refresh, status
sync when fill + position + wallet chain is fully consistent.

**Manual intervention:** wallet mismatch without audit trail.

**Fatal:** fill without consistent position/wallet chain, multiple open positions per symbol,
duplicate deterministic fills, invalid stop monotonicity, fill without order, position without
entry fill.

Recovery requires advisory lock; blocks new entries while active.

## API

Read-only: `/health`, `/readiness`, `/runtime`, `/portfolio`, `/positions`, `/intents`, `/orders`, `/fills`, `/evaluations`, `/audit-events`, `/scheduler-runs`.

Control (disabled by default): `/control/pause`, `/control/resume`, `/control/kill`, `/control/recover`, `/control/run-cycle`.

- `PAPER_CONTROL_API_ENABLED=false` (default) → control routes return 404
- When enabled: `PAPER_CONTROL_API_KEY` required (env only, never stored in DB)
- `compare_digest` for key validation; optional localhost-only policy
- Decimals serialized as strings; timestamps UTC ISO-8601 with `Z`

## Pause / Kill switch

- **Pause:** no new intents/entries; stops and snapshots continue
- **Kill switch (V1):** persistent `FREEZE` only — blocks new entries; does not auto-close open positions; not reset on restart
- **`CLOSE_AT_NEXT_OPEN`:** reserved enum value; rejected fail-closed in config (`PaperTradingConfig`) and API (`POST /control/kill` with unsupported policy returns 422)
- **No exchange execution** in V1 — local paper simulation only

## Accounting verification

Canonical reconstruction sources (no audit-log PnL):

- `paper_fills` with `fill_kind=ENTRY|EXIT` (migration `006_exit_fills`)
- `paper_positions` (entry price, realized PnL, margin)
- `paper_wallet`

```powershell
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL
```

## Phase 9 soak scripts

```powershell
python scripts/run_paper_soak.py --database-url-env PAPER_TRADING_DATABASE_URL --days 365 --seed 1 --reset-db
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL
```

Reference seed=1 (365 days, PostgreSQL): ~17 s, 1026 evaluations, 9 intents, 8 entry fills, 6 closed positions, 100 trailing stop updates, 5 gap + 1 intraday stop, 1 risk rejection, independent accounting OK.

Optional live public soak (testnet, network):

```powershell
$env:HYPERLIQUID_NETWORK = "testnet"
$env:RUN_PAPER_LIVE_SOAK = "1"
python -m pytest tests/paper_trading/soak/test_live_public_data_soak.py -m live -v
```

## Tests

```bash
python -m pytest tests/paper_trading -m "not postgres and not live and not soak" -q
python -m pytest tests/paper_trading -m postgres -q
python -m pytest tests/paper_trading/e2e tests/paper_trading/replay tests/paper_trading/failure -m postgres -q
python -m pytest tests/paper_trading/soak/test_accelerated_soak.py -m "postgres and soak" -q
```

## Production runner (V1)

Start the local paper trading service (public Hyperliquid market data only — no wallet,
no signing, no private endpoints):

```powershell
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://paper_trading_test:<password>@localhost:5432/paper_trading_test"
$env:HYPERLIQUID_NETWORK = "testnet"
python -m alembic upgrade head
python -m services.paper_trading
```

Optional API (readiness/control):

```powershell
$env:PAPER_API_ENABLED = "1"
$env:PAPER_CONTROL_API_ENABLED = "1"
$env:PAPER_CONTROL_API_KEY = "<local-secret>"
python -m services.paper_trading
```

Startup order: config validate → PostgreSQL → migration head → advisory lock → recovery →
Hyperliquid public runtime → market-data readiness → **event bridge + scheduler loop** →
optional FastAPI → heartbeat → `READY`.

See [docs/paper-trading-production-runtime-v1.md](../../docs/paper-trading-production-runtime-v1.md)
for the market-data event contract, idempotency, look-ahead rules, and integration test.

`funding_enabled` remains `False` in V1 (config rejects `True` fail-closed).

## Not approved for unsupervised paper trading

Phase 10 independent read-only audit required before operational deployment.
