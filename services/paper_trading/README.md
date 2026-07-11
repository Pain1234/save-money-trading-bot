# Paper Trading Orchestrator (Phases 1–3)

Implemented scope:

- Domain models, enums, validated configuration, deterministic idempotency keys
- PostgreSQL ORM, Alembic migrations, transactional repository
- Paper accounting adapters and execution engine shared with `backtester.paper_lifecycle`
- Transactional fill service with idempotent persistence

Not implemented yet:

- Scheduler and runtime orchestrator
- Recovery supervisor
- FastAPI control/read API
- Funding processing (disabled by default)
- Dashboard integration

## Dependencies

- `sqlalchemy>=2.0`
- `alembic>=1.13`
- `psycopg[binary]>=3.1`

## Database

Run migrations against PostgreSQL:

```bash
PAPER_TRADING_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/paper_trading alembic upgrade head
```

Singleton tables seeded by migration `004_seed`:

- `runtime_state` (STOPPED)
- `paper_wallet` (cash = 100000)

## Execution parity

Paper fills use the same pure functions as the backtester via `services/backtester/paper_lifecycle.py`:

- Entry slippage and fill-based initial stop
- Post-slippage `RiskEngine.evaluate`
- Gap/intraday stop ordering
- Trailing stop monotonic updates

`SymbolConstraints` must be injected explicitly. Missing constraints fail closed.

## Tests

Offline:

```bash
python -m pytest tests/paper_trading -m "not postgres" -q
```

PostgreSQL integration (requires running database):

```bash
python -m pytest tests/paper_trading/integration -m postgres -v
```
