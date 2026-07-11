# Paper Trading Orchestrator V1 — Implementation Status (Phases 1–3)

## Implemented

### Phase 1 — Domain

- `services/paper_trading/enums.py`
- `services/paper_trading/config.py`
- `services/paper_trading/ids.py`
- `services/paper_trading/models.py`

### Phase 2 — Persistence

- SQLAlchemy ORM (`services/paper_trading/db/`)
- Repository with idempotent inserts (`services/paper_trading/repository.py`)
- Alembic migrations `001`–`004`
- Mandatory `paper_wallet` singleton

### Phase 3 — Execution

- `services/backtester/paper_lifecycle.py` (shared math with backtester)
- `services/paper_trading/accounting.py`
- `services/paper_trading/execution.py` (`PaperExecutionEngine`, `PaperFillService`)
- `services/paper_trading/mapping.py`

## Idempotency

| Entity | Key |
|--------|-----|
| Strategy evaluation | `(strategy_version, symbol, daily_candle_open_time)` |
| Trade intent | `(strategy_evaluation_id, symbol, side, signal_type)` + `build_client_intent_id` |
| Paper fill | `(paper_order_id, candle_key, fill_sequence)` |
| Funding event | `(position_id, funding_time)` |
| Scheduler run | `(job_name, scheduled_for)` |

## Transaction boundaries

`PaperFillService.execute_scheduled_paper_fill` writes intent status, order, fill, position, wallet, and audit event in one database transaction.

## V1 exit policy

Position exits in V1 are stop-based only (initial, trailing, gap). No monthly/weekly regime closes.

## PostgreSQL test status

Integration tests are marked `@pytest.mark.postgres` and require `PAPER_TRADING_DATABASE_URL` pointing to a reachable PostgreSQL instance.

## Not approved for live paper trading

Phases 4–10 (scheduler, recovery, API, full integration) are not yet implemented.
