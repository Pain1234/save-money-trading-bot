# Paper Trading Orchestrator (Phases 1–6)

## Scope

Phases 1–6 implement domain, PostgreSQL persistence, execution parity with the backtester, evaluation/intent/fill lifecycle, stop/close/portfolio snapshots, and an internal scheduler with advisory lock and composite readiness.

Not implemented: recovery supervisor (Phase 7), FastAPI control API, wallet/signing, real exchange orders.

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
| `runtime.py` | Runtime state machine, pause, kill |
| `lock.py` | PostgreSQL advisory lock |

## ATR semantics

- **Entry:** `entry_atr14` persisted on `paper_positions` at fill time (frozen).
- **Trailing update:** current daily evaluation ATR when available, else `entry_atr14` (matches backtester).

## Scheduler jobs

1. `readiness_check`
2. `daily_signal_evaluation`
3. `next_open_fill_processing`
4. `daily_stop_update`
5. `stop_trigger_processing`
6. `funding_processing` (only if `funding_enabled=true`)
7. `portfolio_snapshot`
8. `runtime_heartbeat`

**Daily open:** fills → stops → funding (optional) → snapshot  
**Daily close + delay:** evaluation → trailing → snapshot

## PostgreSQL verification

**Status: PostgreSQL nicht live verifiziert** (no Docker/local PG during last run).

Use `docker/docker-compose.paper-test.yml` and:

```powershell
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
python -m alembic upgrade head
python -m pytest tests/paper_trading/integration -m postgres -v
```

## Tests

```bash
python -m pytest tests/paper_trading -m "not postgres" -q
```

## Not approved for unsupervised paper trading

Recovery and API layers are still required.
