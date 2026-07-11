# Paper Trading Orchestrator V1 — Phase 9 E2E, Replay, Crash, Recovery, Soak

## Scope

Phase 9 validates the full local paper-trading path without exchange execution:

Market Data → Strategy Evaluation → persistent evaluation → Trade Intent → Next-Open Paper Fill → Paper Position → Trailing Stop → Stop Exit → Wallet → Portfolio Snapshot → Audit Events → Scheduler → Recovery → API.

No Hyperliquid private endpoints, wallet, signing, or real orders.

## Test layout

| Directory | Purpose |
|-----------|---------|
| `tests/paper_trading/e2e/` | Full lifecycle, multi-symbol, pause/kill, restart, API |
| `tests/paper_trading/replay/` | Backtester ↔ paper orchestrator parity, replay idempotency |
| `tests/paper_trading/failure/` | Crash boundaries, DB interruptions, scheduler lock contention |
| `tests/paper_trading/soak/` | Accelerated 365-day soak, optional live public-data soak |
| `scripts/run_paper_soak.py` | CLI soak runner with JSON report |
| `scripts/verify_paper_state.py` | Independent aggregate and invariant verification |

## E2E flows verified

### Deterministic BTC lifecycle

- Monthly/weekly regime positive, daily breakout signal
- Evaluation persisted once; intent scheduled for next daily open
- No fill at signal close; fill at next open with slippage
- Initial stop from actual fill price; risk re-check after slippage/rounding
- Trailing stop monotonic over rising closes
- Gap/intraday stop exit; margin release; wallet/PnL/fees with `Decimal`
- Portfolio snapshot and audit events complete
- Full replay produces no duplicate evaluations, intents, fills, or positions

### Multi-symbol (BTC → ETH → SOL)

- Max three positions, one per symbol; portfolio risk ≤ 2 %, per-trade ≤ 0.5 %, leverage ≤ 2×
- Equity decreases correctly after prior fills
- Fourth symbol blocked; duplicate symbol blocked; nonterminal intent blocks duplicate
- Risk rejection of one symbol does not corrupt others

### Pause / Kill switch

- Pause: no new evaluations/intents/entry fills; stops and snapshots continue; survives restart
- Kill FREEZE: persistent; no new intents/fills; not reset on restart
- Kill CLOSE_AT_NEXT_OPEN: local exit planning only at next open; idempotent

### Restart / Recovery (PostgreSQL)

Crash injection at transaction boundaries A–L (evaluation → intent → order → fill → position → wallet → audit → stop → close → snapshot → scheduler RUNNING → stale heartbeat).

After `recover_on_startup()`:

- No duplicate evaluations, intents, orders, fills, positions, wallet debits, stop exits, or audit events
- Runtime reaches `READY` only when consistent; financial ambiguity → `FAILED`, `entry_readiness=False`

## Backtester–paper replay parity

Identical candle fixtures and configuration compared field-by-field (no float tolerance):

- Evaluation times, entry type, fill time/price, quantity, initial stop
- Stop updates, exit time/price, fees, margin, realized PnL, final cash/equity
- Rejection reasons and BTC/ETH/SOL ordering

Scenarios: breakout, pullback, breakout-over-pullback priority, gap stop, intraday stop, same-candle stop, post-rounding risk rejection, position limit, portfolio risk limit.

No parity regressions found after Phase 9 product fixes (see below).

## Scheduler idempotency and lock contention

- Two concurrent scheduler processes: only one advisory lock holder executes jobs
- Lock released on shutdown, connection close, and exception
- Duplicate scheduler runs deduplicated; `COMPLETED` not re-run; `RUNNING` not parallel
- Naive `scheduled_for` rejected; UTC normalization enforced
- Daily open order: entry fills → stop trigger → funding (if enabled) → snapshot
- Daily close order: evaluation → trailing stop → snapshot

## API E2E (PostgreSQL state)

Read: `/health`, `/readiness`, `/runtime`, `/portfolio`, `/positions`, `/intents`, `/orders`, `/fills`, `/evaluations`, `/audit-events`, `/scheduler-runs`.

Verified:

- Decimals as strings; UTC timestamps with `Z` on response models
- Stable cursor pagination; filters read-only
- No ORM objects, DB URL, env vars, API keys, or stack traces in responses
- `/readiness` → 503 when entry readiness false
- Control disabled by default (404); valid API key required; wrong key rejected and never stored
- Pause/resume/run-cycle transactional and idempotent

## Soak scenarios

### Accelerated 365-day soak (pytest + CLI)

- Injected clock; no real-time waits
- BTC, ETH, SOL; monthly/weekly/daily data; multiple signals and quiet periods
- Periodic double-scheduler calls, simulated restart, degraded readiness, pause toggles, recovery
- Per-day invariant checks: no duplicates, position limits, stop monotonicity, wallet consistency, no NaN/Inf
- **Measured (seed=1, local PostgreSQL):** ~0.66 s elapsed, 132 evaluations, 1 intent, 0 fills, 133 audit events (fixture-driven signal density)

### Optional live public-data soak

- Skipped unless `RUN_PAPER_LIVE_SOAK=1` and `HYPERLIQUID_NETWORK=testnet`
- Public meta/candle/WebSocket only; no wallet, signing, or orders
- Default offline pytest suite uses no network

## Product fixes during Phase 9

| Fix | Reason |
|-----|--------|
| `transaction_scope()` with nested savepoints | Nested `session.begin()` broke E2E/recovery tests inside fixture transactions |
| Preserve closed position quantity | Zeroing quantity on close violated `ck_paper_positions_quantity_positive` |
| `RuntimeService` import in `api.py` | Control endpoints raised `NameError` at runtime |
| E2E fill context uses evaluation ATR | Hardcoded ATR caused spurious `RC_REJECT_DATA` fills |

## Verification commands

```powershell
$env:PAPER_TRADING_DATABASE_URL = "postgresql+psycopg://paper_trading_test:<LOCAL_PASSWORD>@localhost:5432/paper_trading_test"

python -m pytest tests/strategy_engine tests/risk_engine tests/backtester tests/market_data tests/paper_trading -m "not postgres and not live and not soak" -q
python -m pytest tests/paper_trading -m postgres -q
python -m pytest tests/paper_trading/e2e tests/paper_trading/replay tests/paper_trading/failure -m postgres -q
python -m pytest tests/paper_trading/soak/test_accelerated_soak.py -m "postgres and soak" -q
python scripts/run_paper_soak.py --database-url-env PAPER_TRADING_DATABASE_URL --days 365 --seed 1
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL
python -m pytest tests/backtester -q
python -m mypy services/strategy_engine services/risk_engine services/backtester services/market_data services/paper_trading
python -m ruff check services tests migrations scripts
```

## Remaining risks

- Live testnet public soak not run in CI by default; transport edge cases may differ from fixtures
- Accelerated soak uses deterministic generated candles, not full production market-data pipeline
- Single-process API control tests; multi-instance deployment locking not load-tested
- No independent Phase 10 read-only audit yet — **not approved for unsupervised paper trading**

## Status

Phase 9 implementation and automated verification complete. Final operational approval requires Phase 10 independent audit.
