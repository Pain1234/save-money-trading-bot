# Paper Trading Orchestrator (Phases 1–8)

## Scope

Phases 1–8 implement domain, PostgreSQL persistence, execution parity with the backtester, evaluation/intent/fill lifecycle, stop/close/portfolio snapshots, internal scheduler, composite readiness, deterministic recovery, and a FastAPI read/control plane.

Not implemented: Hyperliquid private API, wallet/signing, real exchange orders (Phases 9–10).

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
python -m pytest tests/paper_trading/integration -m postgres -v
```

Alternative: `docker/docker-compose.paper-test.yml` on port `5433`.

## Migrations

Alembic revisions `001`–`005`. Verify with:

```powershell
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
python scripts/verify_pg_schema.py
```

## Recovery policy

Startup flow: `STARTING → RECOVERING → SYNCING → READY` (or `DEGRADED` / `FAILED`).

**Auto-repairable:** orphan `RUNNING` scheduler runs, stale heartbeat refresh, `OPEN` order with fill → `FILLED`, intent status sync when fill exists.

**Manual intervention:** fill without position, position without entry fill, `CLOSING` without exit, wallet mismatch without audit trail.

**Fatal:** multiple open positions per symbol, duplicate deterministic fills, invalid stop monotonicity, fill without order.

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
- **Kill switch:** persistent; blocks new entries; not reset on restart
- **No exchange execution** in V1 — local paper simulation only

## Tests

```bash
python -m pytest tests/paper_trading -m "not postgres" -q
python -m pytest tests/paper_trading/integration -m postgres -v
python -m pytest tests/paper_trading/test_api_read.py tests/paper_trading/test_api_control.py tests/paper_trading/test_api_security.py -q
```

## Not approved for unsupervised paper trading

End-to-end and soak tests (Phases 9–10) remain before operational deployment.
