# Paper Trading Orchestrator V1 — Implementation Status (Phases 1–6)

## Implemented

### Phase 1 — Domain

- `services/paper_trading/enums.py`, `config.py`, `ids.py`, `models.py`

### Phase 2 — Persistence

- SQLAlchemy ORM, repository, Alembic migrations `001`–`005`
- Mandatory `paper_wallet` singleton

### Phase 3 — Execution

- `services/backtester/paper_lifecycle.py` (shared with backtester)
- `PaperExecutionEngine`, `PaperFillService`

### Phase 4 — Evaluation, Intents, Fill Lifecycle

- `clock.py` — injectable UTC clock (no `datetime.now()` in domain)
- `evaluation.py` — `evaluate_symbol_for_daily_close`
- `lifecycle.py` — intent creation, `process_scheduled_intents_for_open`
- `transitions.py` — intent/order/runtime state machines
- `orchestrator.py` — facade

**Evaluation flow:** market data ready → closed candles only → `StrategyEngine.evaluate()` → persist evaluation (idempotent) → optional scheduled intent at next daily open (no same-close fill).

**Intent gates:** entry readiness, pause, kill switch, existing position/intent, max 3 positions, ATR, valid signal.

**Fill flow:** BTC → ETH → SOL; mandatory re-risk at fill via `PaperFillService`.

### Phase 5 — Stops, Close, Portfolio

- `stops.py` — trailing stop update, gap/intraday stop triggers (backtester parity)
- `portfolio.py` — idempotent portfolio snapshots
- Migration `005`: `paper_positions.entry_atr14`, `portfolio_snapshots.idempotency_key`

**ATR semantics (backtester parity):** trailing stop update uses **current daily evaluation ATR** when available, else **persisted `entry_atr14`** at position open. Entry ATR is frozen at fill time.

**Stop order:** gap at open, then intraday low; same-candle stop after entry fill (conservative).

**Funding:** disabled by default (`funding_enabled=false`); models/repository only.

### Phase 6 — Scheduler, Lock, Readiness

- `scheduler.py` — jobs A–H, daily open/close sequences
- `readiness.py` — `process_liveness`, `runtime_readiness`, `entry_readiness`
- `runtime.py` — validated runtime transitions, heartbeat, pause/kill
- `lock.py` — PostgreSQL `pg_try_advisory_lock` + test double

**Daily open job order:** fills → stop triggers → (optional funding) → snapshot

**Daily close + delay:** evaluation → trailing stop update → snapshot

**Pause:** blocks evaluations/intents/fills; stops and snapshots continue.

**Kill switch:** persistent; blocks new entries; not reset on restart.

## PostgreSQL verification status

**PostgreSQL nicht live verifiziert** on this machine: Docker and local PostgreSQL were unavailable during Gate 0.

Infrastructure prepared:

- `docker/docker-compose.paper-test.yml` (PostgreSQL 16, port `5433`, DB `paper_trading_test`)

To verify locally:

```powershell
docker compose -f docker/docker-compose.paper-test.yml up -d
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/paper_trading_test"
python -m alembic upgrade head
python -m pytest tests/paper_trading/integration -m postgres -v
```

## Not implemented (Phase 7+)

- Recovery supervisor
- FastAPI / Control API / Dashboard
- Hyperliquid private API, wallet, signing, real orders

## Not approved for unsupervised paper trading

Recovery and API layers are required before operational deployment.
