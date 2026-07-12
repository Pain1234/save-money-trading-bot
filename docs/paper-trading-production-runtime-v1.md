# Paper Trading Production Runtime V1 — Market-Data Event Lifecycle

## Overview

The production runner closes the remaining lifecycle gap: public Hyperliquid market data
now drives daily open, live intraday, and daily close processing through the scheduler
without manual test context registration.

No wallet, signing, or private exchange endpoints are used.

## Architecture

```
HyperliquidMarketDataRuntime.process_live()
  → InMemoryCandleRepository
  → MarketEventDetector.detect_candidates()
  → MarketEventBridge.process_after_poll()
  → ProductionContextBuilder (Evaluation / Fill / Stop contexts)
  → PaperTradingScheduler sequences / jobs
  → MarketEventDetector.acknowledge_completed() on terminal success
  → PostgreSQL (fills, positions, wallet, scheduler_runs)
```

### Modules

| Module | Role |
|--------|------|
| `market_events.py` | Candidate detection, deferred retry, post-success acknowledgement |
| `scheduler_context.py` | Production scheduler inputs from market data |
| `symbol_constraints.py` | Hyperliquid `szDecimals` or env JSON (fail-closed) |
| `controlled_market_data.py` | Scriptable runtime for integration tests |
| `application.py` | Runner loop: poll → bridge → commit → readiness |

## Market event contract

| Event | Trigger | Actions |
|-------|---------|---------|
| `DAILY_OPEN_AVAILABLE` | New daily candle; open known | Gap stop at open, entry fill after `fill_delay_seconds`, snapshot |

Daily open subjobs (independent idempotency):

- `me:do:gap:{symbol}:{open_time}` — gap stop at open (not delayed by fill)
- `me:do:fill:{symbol}:{open_time}` — entry fill when due
- `me:do:snap:{symbol}:{open_time}` — portfolio snapshot after economic change

The umbrella key `me:do:{symbol}:{open_time}` tracks overall open lifecycle completion.
| `DAILY_LIVE_UPDATE` | Open candle low changes | Intraday stop only (no trailing, no gap re-check) |
| `DAILY_CLOSED` | Daily closed **and** `clock.now() >= evaluation_due_at` | Evaluation + intent, trailing stop, snapshot |
| `WEEKLY_CLOSED` / `MONTHLY_CLOSED` | Higher TF closed | Marker only; series ready for later evaluation |

### Daily close due-time semantics

- `evaluation_due_at = daily_close_time + evaluation_delay_seconds` (default 5s)
- `MarketEventDetector` emits `DAILY_CLOSED` only when `clock.now() >= evaluation_due_at`
- Polls before due are **not errors**: no scheduler run, no FAILED status, no event consumption
- Provider close inside the delay window does not consume the daily evaluation; processing runs once after due
- The bridge retains a belt-and-suspenders guard in `_handle_daily_closed` for defense in depth

## Idempotency keys

Deterministic scheduler job names (no `hash()`):

- `me:do:{symbol}:{open_time}` — daily open lifecycle marker
- `me:do:gap:{symbol}:{open_time}` / `me:do:fill:{symbol}:{open_time}` / `me:do:snap:{symbol}:{open_time}` — open subjobs
- `me:dl:{symbol}:{open_time}:{low_digest}` — daily live update
- `me:dc:{symbol}:{open_time}` — daily closed evaluation
- `me:wc:{symbol}:{open_time}` / `me:mc:{symbol}:{open_time}` — higher TF markers

Completed market-event runs skip reprocessing on restart, WebSocket replay, and backfill.

## Look-ahead boundaries

- Gap check: candle **open** only (`_gap_check_strategy_candle`)
- Intraday check: observed **low** on open preview candle
- Daily evaluation: after `close_time + evaluation_delay_seconds` (detector defers emission until due)
- Trailing stop: only on **closed** daily candles
- Injectable `Clock` for all scheduling decisions (no bare `datetime.now()` in domain)

## Scheduler context generation

`ProductionContextBuilder` assembles:

- `EvaluationContext` — `StrategyDataBundle`, gates, `SymbolConstraints`
- `FillContext` — open ref, ATR, prior closes, day candles (open-only for gap safety)
- `StopContext` — gap / intraday preview / trailing on closed daily

Construction requires an explicit `market_data_ready` callable (no default `True`). Missing readiness source fails closed at construction time; a `False` runtime snapshot blocks entry gates.

Construction requires an explicit `market_data_ready` callable (no default `True`). Missing readiness source fails closed at construction time; a `False` runtime snapshot blocks entry gates.

Open-context errors are typed (no string matching):

- `RETRYABLE_CONTEXT_NOT_READY` — transient bundle/ATR/DB visibility; event stays retryable, runtime may be `DEGRADED`
- `PERMANENT_CONFIGURATION_FAILURE` — missing/invalid constraints; `FAILED` run, `entry_readiness=False`
- `FILL_NOT_DUE` — gap may complete; fill/snapshot deferred until `open_time + fill_delay_seconds`

## Event lifecycle semantics

1. `detect_candidates()` emits events without irreversible tracker mutation.
2. Bridge checks capacity, builds context, runs scheduler jobs/subjobs.
3. `acknowledge_completed(event)` runs only after terminal success (`COMPLETED` subjobs for open).
4. Transient failures return deferred outcomes — no terminal `FAILED`, tracker unchanged, retry on next poll.
5. Queue overflow processes the first `max_events_per_poll` batch; unprocessed candidates re-emit on the next poll.

Tracker fields (`daily_open_ack_time`, etc.) update only via acknowledgement.

## Runner loop

1. Poll live market data (`process_live`)
2. Detect event candidates (bounded: default 256/poll)
3. Build contexts and run scheduler sequences / open subjobs
4. Acknowledge completed events; leave deferred/backlog events unacknowledged
5. Commit repository session
6. Update runtime readiness (`READY` / `DEGRADED` on disconnect, deferred backlog, or overflow)
7. Heartbeat on separate task
8. Graceful shutdown cancels tasks, releases advisory lock

### Backpressure

If detected events exceed `max_events_per_poll`, the bridge sets `queue_overflow=True`,
processes the first batch only, and leaves remaining candidates for the next poll.
Readiness goes `DEGRADED` while backlog or deferred critical events remain.

## PostgreSQL test concurrency

The postgres fixture truncates shared tables in `paper_trading_test`. Do **not** run postgres-marked
paper-trading tests with pytest-xdist workers against the same database. Release gates:

```bash
python -m pytest tests/paper_trading -m postgres -n 1 -vv
```

## Symbol constraints

Production path (in order):

1. `PAPER_SYMBOL_CONSTRAINTS_JSON` env override (all symbols required)
2. Hyperliquid meta `szDecimals` → quantity step and price tick

No hardcoded tick/step fallbacks in production.

## PostgreSQL test fixture safety

The autouse `@pytest.mark.postgres` reset fixture calls `SELECT current_database(), current_user`
on the **actual connection** before any `TRUNCATE`. Destructive resets run only when
`current_database()` is exactly `paper_trading_test`. Wrong database → immediate exception,
no mutation, no credentials in the error message. The fixture never runs in the production runner.

## Integration test (15 steps)

`tests/paper_trading/integration/test_production_lifecycle_full.py` exercises:

startup wiring, advisory lock, controlled market data, closed daily evaluation, intent
without same-close fill, next-open entry, live low above stop, intraday exit, restart
idempotency, and passive second lock holder.

Requires writable PostgreSQL (`postgres_runtime_writable` fixture skips on stale locks).

## Testnet soak

Uses `tests/paper_trading/soak/test_live_public_data_soak.py` through the real
`PaperTradingApplication` path. The soak asserts (when `RUN_PAPER_LIVE_SOAK=1`):

- Hyperliquid meta loaded and backfill complete for BTC/ETH/SOL (1D/1W/1M VALID)
- WebSocket CONNECTED with 9/9 subscription ACKs
- `market_data_ready() == True` and runtime READY/DEGRADED
- Multiple persisted heartbeat scheduler runs
- No orphan RUNNING jobs after shutdown; advisory lock re-acquirable
- `verify_paper_state` exit 0; HTTP/WebSocket/DB/engine/tasks cleaned up
- Duration ≥ 300s, total timeout ≤ 420s

```powershell
$env:PAPER_TRADING_DATABASE_URL = "<LOCAL TEST DB>"
$env:HYPERLIQUID_NETWORK = "testnet"
$env:RUN_PAPER_LIVE_SOAK = "1"
$env:PAPER_LIVE_SOAK_SECONDS = "300"
python -m pytest tests/paper_trading/soak/test_live_public_data_soak.py -m live -v -s
```

Remove env vars after the run.

## Verification commands

```powershell
python -m pytest tests/strategy_engine tests/risk_engine tests/backtester tests/market_data tests/paper_trading -m "not postgres and not live and not soak" -q
python -m pytest tests/paper_trading -m postgres -v
python -m pytest tests/paper_trading/integration -k "production or runner" -v
python -m mypy services/strategy_engine services/risk_engine services/backtester services/market_data services/paper_trading
python -m ruff check services tests migrations scripts
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL
```
