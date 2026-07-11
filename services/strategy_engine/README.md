# SAVE-MONEY BOT Strategy Engine

Deterministic Python implementation of **Strategy Specification V1.0 (Specification Freeze)**.

## Public Interface

```python
from datetime import datetime, timezone
from strategy_engine import (
    StrategyEngine,
    StrategyParameters,
    Candle,
    CandleSeries,
    Timeframe,
    compute_initial_stop,
    update_trailing_stop,
)

engine = StrategyEngine()
evaluation = engine.evaluate(
    daily=daily_series,
    weekly=weekly_series,
    monthly=monthly_series,
    evaluation_time=datetime(2024, 6, 1, 0, 0, 5, tzinfo=timezone.utc),
    parameters=StrategyParameters(),  # optional; defaults = Spec Freeze 1.0
)
```

### Trailing Stop (post-entry)

```python
from strategy_engine import TrailingStopState, initialize_trailing_stop

state = initialize_trailing_stop(
    entry_price=entry,
    atr14_at_entry=atr,
    stop_initial=stop,
    params=StrategyParameters(),
)
state = update_trailing_stop(state, close_t=close, atr14_daily_t=atr_t, params=params)
```

## Expected Input Data

### Candle

| Field | Type | Requirement |
|---|---|---|
| `symbol` | `str` | e.g. `BTC`, `ETH`, `SOL` |
| `timeframe` | `Timeframe` | `1D`, `1W`, `1M` |
| `open_time` | UTC `datetime` | Candle open |
| `close_time` | UTC `datetime` | Inclusive close |
| `open`, `high`, `low`, `close` | `Decimal` | > 0, valid OHLC |
| `volume` | `Decimal` | ≥ 0 |
| `is_closed` | `bool` | Must be `True` |

### CandleSeries

- Strictly ascending `open_time`
- No duplicate timestamps
- Same `symbol` and `timeframe` for all candles
- Warmup minimums: Daily ≥ 21, Weekly ≥ 50, Monthly ≥ 20

### evaluation_time

Explicit UTC timestamp passed by caller. Must be `>= close_time` of all candles used. **No system clock** is used inside the engine.

## Output Model: StrategyEvaluation

| Field | Description |
|---|---|
| `symbol` | Evaluated symbol |
| `evaluation_time` | Passed evaluation timestamp |
| `strategy_version` | `1.0.0` |
| `parameters` | Parameters used |
| `monthly_regime` | `RegimeResult` |
| `weekly_trend` | `TrendResult` |
| `breakout_result` / `pullback_result` | Entry setup details |
| `indicators` | `IndicatorSnapshot` at index `t` |
| `volume_ratio`, `atr` | Key daily values |
| `selected_entry_type` | `BREAKOUT`, `PULLBACK`, or `None` |
| `signal_intent` | `LONG_ENTRY`, `NO_ENTRY`, `INVALID_DATA`, `INSUFFICIENT_HISTORY` |
| `reason_codes` | Tuple of `ReasonCode` |
| `data_quality_status` | `OK`, `INVALID_DATA`, `INSUFFICIENT_HISTORY` |

## Reason Codes

See `strategy_engine.models.ReasonCode` — aligned with Strategy Spec §10:

- Entry: `RC_ENTRY_BREAKOUT_20D`, `RC_ENTRY_PULLBACK_EMA20`
- Exit (stops module): `RC_EXIT_STOP_INITIAL`, `RC_EXIT_STOP_TRAILING`, `RC_EXIT_STOP_GAP`
- Reject: `RC_REJECT_REGIME`, `RC_REJECT_TREND`, `RC_REJECT_VOLUME`, `RC_REJECT_WARMUP`, `RC_REJECT_DATA`, `RC_REJECT_NO_SIGNAL`, …

## Example Evaluation

```python
# After warmup, flat market → no entry
evaluation.signal_intent.kind  # SignalIntentKind.NO_ENTRY
evaluation.reason_codes        # (RC_REJECT_NO_SIGNAL,)

# Breakout day
evaluation.signal_intent.kind           # LONG_ENTRY
evaluation.selected_entry_type          # BREAKOUT
evaluation.signal_intent.entry_price    # Daily close C[t]
evaluation.signal_intent.stop_initial   # C[t] - 2.5 * ATR14[t]
```

## Default Parameters (Specification Freeze 1.0)

| Parameter | Default |
|---|---|
| `volume_ratio_min` | **1.00** |
| `pullback_ema_tolerance` | 0.005 |
| `stop_initial_atr_mult` | 2.5 |
| `trail_atr_mult` | 3.0 |
| `daily_ema_period` | 20 |
| `weekly_ema_fast` / `weekly_ema_slow` | 20 / 50 |
| `monthly_ema_period` | 20 |
| `breakout_lookback` | 20 |
| `atr_period` | 14 |
| `volume_sma_period` | 20 |

## Test Commands

```bash
pip install -e ".[dev]"
pytest tests/strategy_engine -v
mypy services/strategy_engine
ruff check services/strategy_engine tests/strategy_engine
```

## Scope (Not Implemented)

- Order execution, Hyperliquid API
- Risk Engine, portfolio management
- Database, WebSockets, paper trading
- Dashboard integration

## Module Layout

```
services/strategy_engine/
  models.py       # Pydantic data models
  constants.py    # Spec Freeze defaults
  validation.py   # Candle validation (fail-closed)
  indicators.py   # EMA, ATR, Volume Ratio, High20
  regime.py       # Monthly regime
  trend.py        # Weekly trend
  entry.py        # Breakout, Pullback, priority
  stops.py        # Initial & trailing stops
  engine.py       # StrategyEngine.evaluate()
```
