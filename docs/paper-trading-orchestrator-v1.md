# Paper Trading Orchestrator V1 — Implementation Status (Phases 1–9)

## Implemented

### Phases 1–6

See prior sections: domain, persistence, execution, lifecycle, stops/portfolio, scheduler/readiness.

### Phase 7 — Recovery

- `recovery.py` — consistency checks, auto-repair, `recover_on_startup()`
- Runtime transitions: `STARTING → RECOVERING → SYNCING → READY`
- Checks: orphan scheduler runs, intent/order/fill chain, position references, stop invariants, duplicate fills
- Auto-repair: orphan runs → `FAILED`, order/intent status sync, stale heartbeat
- Fatal: multiple open positions per symbol, duplicate fills, broken stop history
- Failure-injection tests with real PostgreSQL savepoints

### Phase 8 — FastAPI

- `api.py`, `api_models.py`, `api_dependencies.py`
- Read plane with pagination, Decimal-as-string, UTC-with-Z
- Control plane gated by `PAPER_CONTROL_API_ENABLED` + `PAPER_CONTROL_API_KEY`
- Optional deps: `fastapi>=0.110`, `uvicorn[standard]>=0.27`

### Phase 9 — E2E, Replay, Crash, Recovery, Soak

- E2E: full BTC lifecycle, multi-symbol limits, pause/kill, restart recovery, API against PostgreSQL
- Replay: backtester parity and idempotency
- Failure: crash boundaries, DB interruptions, advisory-lock contention
- Soak: 365-day accelerated soak; `scripts/run_paper_soak.py`, `scripts/verify_paper_state.py`
- Optional live public testnet soak (network; skipped by default)

**Kill switch (V1):** only `KillSwitchClosePolicy.FREEZE` is supported. `CLOSE_AT_NEXT_OPEN` is reserved for a future execution version and is rejected fail-closed in config and API control. FREEZE blocks new entries; open positions are not auto-closed; trailing stops continue during pause.

**Accounting verification:** canonical sources are `paper_fills` (ENTRY and EXIT), `paper_positions`, and `paper_wallet`. Stop exits persist as EXIT fills (migration `006_exit_fills`). Audit events are not used to reconstruct PnL.

See [paper-trading-e2e-soak-v1.md](./paper-trading-e2e-soak-v1.md) for detailed results.

### Production runtime (market-data event lifecycle)

- `market_events.py` — detect `DAILY_OPEN_AVAILABLE`, `DAILY_LIVE_UPDATE`, `DAILY_CLOSED`
- `scheduler_context.py` — production Evaluation/Fill/Stop contexts from market data
- `application.py` — runner loop: poll → event bridge → scheduler → commit → readiness
- `symbol_constraints.py` — Hyperliquid meta `szDecimals` or `PAPER_SYMBOL_CONSTRAINTS_JSON`
- See [paper-trading-production-runtime-v1.md](./paper-trading-production-runtime-v1.md)

## PostgreSQL verification status

**Live verified** on local PostgreSQL 16.14 (`localhost:5432`, database `paper_trading_test`).

- Migrations: upgrade/downgrade roundtrip OK
- 54 PostgreSQL integration/E2E tests passing
- Schema verified via `scripts/verify_pg_schema.py`
- Independent state verification via `scripts/verify_paper_state.py`

## Remaining (Phase 10)

- Independent read-only operational audit
- Production deployment hardening
- Hyperliquid private API, wallet, signing, real orders — **not in scope**

## Not approved for unsupervised paper trading

Phase 10 independent audit required before operational deployment.
