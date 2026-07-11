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
  → MarketEventDetector.detect()
  → MarketEventBridge.process_after_poll()
  → ProductionContextBuilder (Evaluation / Fill / Stop contexts)
  → PaperTradingScheduler sequences / jobs
  → PostgreSQL (fills, positions, wallet, scheduler_runs)
```

### Modules

| Module | Role |
|--------|------|
| `market_events.py` | Event detection, idempotent bridge, overflow fail-closed |
| `scheduler_context.py` | Production scheduler inputs from market data |
| `symbol_constraints.py` | Hyperliquid `szDecimals` or env JSON (fail-closed) |
| `controlled_market_data.py` | Scriptable runtime for integration tests |
| `application.py` | Runner loop: poll → bridge → commit → readiness |

## Market event contract

| Event | Trigger | Actions |
|-------|---------|---------|
| `DAILY_OPEN_AVAILABLE` | New daily candle; open known | Next-open fills, gap stops (`at_open=True`), snapshot |
| `DAILY_LIVE_UPDATE` | Open candle low changes | Intraday stop only (no trailing, no gap re-check) |
| `DAILY_CLOSED` | Daily closed at evaluation time | Evaluation + intent, trailing stop, snapshot |
| `WEEKLY_CLOSED` / `MONTHLY_CLOSED` | Higher TF closed | Marker only; series ready for later evaluation |

## Idempotency keys

Deterministic scheduler job names (no `hash()`):

- `market_event:daily_open:{symbol}:{open_time}`
- `market_event:daily_live:{symbol}:{open_time}:low:{observed_low}`
- `market_event:daily_closed:{symbol}:{open_time}`

Completed market-event runs skip reprocessing on restart, WebSocket replay, and backfill.

## Look-ahead boundaries

- Gap check: candle **open** only (`_gap_check_strategy_candle`)
- Intraday check: observed **low** on open preview candle
- Daily evaluation: after `close_time + evaluation_delay_seconds`
- Trailing stop: only on **closed** daily candles
- Injectable `Clock` for all scheduling decisions (no bare `datetime.now()` in domain)

## Scheduler context generation

`ProductionContextBuilder` assembles:

- `EvaluationContext` — `StrategyDataBundle`, gates, `SymbolConstraints`
- `FillContext` — open ref, ATR, prior closes, day candles (open-only for gap safety)
- `StopContext` — gap / intraday preview / trailing on closed daily

Missing constraints → context build returns `None` → event processing fails closed.

## Runner loop

1. Poll live market data (`process_live`)
2. Detect and classify events (bounded: default 256/poll)
3. Build contexts and run scheduler sequences
4. Commit repository session
5. Update runtime readiness (`READY` / `DEGRADED` on disconnect or overflow)
6. Heartbeat on separate task
7. Graceful shutdown cancels tasks, releases advisory lock

### Backpressure

If detected events exceed `max_events_per_poll`, the bridge sets `queue_overflow=True`,
returns `event_queue_overflow`, and readiness goes fail-closed.

## Symbol constraints

Production path (in order):

1. `PAPER_SYMBOL_CONSTRAINTS_JSON` env override (all symbols required)
2. Hyperliquid meta `szDecimals` → quantity step and price tick

No hardcoded tick/step fallbacks in production.

## Integration test (15 steps)

`tests/paper_trading/integration/test_production_lifecycle_full.py` exercises:

startup wiring, advisory lock, controlled market data, closed daily evaluation, intent
without same-close fill, next-open entry, live low above stop, intraday exit, restart
idempotency, and passive second lock holder.

Requires writable PostgreSQL (`postgres_runtime_writable` fixture skips on stale locks).

## Testnet soak

Uses existing `tests/paper_trading/soak/test_live_public_data_soak.py` through the real
`PaperTradingApplication` path (meta, backfill, WebSocket, bridge, heartbeat).

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
