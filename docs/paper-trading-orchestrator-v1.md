# Paper Trading Orchestrator V1 — Implementation Status (Phases 1–8)

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

## PostgreSQL verification status

**Live verified** on local PostgreSQL 16.14 (`localhost:5432`, database `paper_trading_test`).

- Migrations: upgrade/downgrade roundtrip OK
- 24 PostgreSQL integration tests passing (including recovery, failure injection, API)
- Schema verified via `scripts/verify_pg_schema.py`

## Remaining (Phases 9–10)

- End-to-end orchestrator soak tests
- Production deployment hardening
- Hyperliquid private API, wallet, signing, real orders — **not in scope**

## Not approved for unsupervised paper trading

Soak and E2E validation (Phases 9–10) required before operational deployment.
