# Strategy V1 — Parameter Inventory (Specification Freeze 1.0)

This document publishes the **explicit parameter inventory** for Strategy V1 and its coupled Risk V1 defaults.

**Sources of truth:**

- Specification: `docs/strategy-specification.md` (Freeze table)
- Strategy defaults (code): `services/strategy_engine/constants.py`, `services/strategy_engine/models.py`
- Risk defaults (code): `services/risk_engine/constants.py`, `services/risk_engine/models.py`, `services/risk_engine/validation.py`

**Change control (binding):**

- Any change to these parameters or their defaults requires **a dedicated GitHub issue + PR review**.
- Agents must not change parameters “while fixing something else” (see `AGENTS.md`).

---

## Strategy Engine (StrategyParameters)

**Code model:** `services/strategy_engine/models.py::StrategyParameters`  
**Default constants:** `services/strategy_engine/constants.py`

| Parameter | Spec name | Default (Freeze 1.0) | Type | Notes |
|---|---|---:|---|---|
| `strategy_version` | `STRATEGY_VERSION` | `1.0.0` | `str` | Must match spec version header |
| `monthly_ema_period` | `MONTHLY_EMA_PERIOD` | `20` | `int` | Monthly regime filter |
| `weekly_ema_fast` | `WEEKLY_EMA_FAST` | `20` | `int` | Weekly trend filter |
| `weekly_ema_slow` | `WEEKLY_EMA_SLOW` | `50` | `int` | Weekly trend filter |
| `daily_ema_period` | `DAILY_EMA_PERIOD` | `20` | `int` | Daily EMA for entries |
| `breakout_lookback` | `BREAKOUT_LOOKBACK` | `20` | `int` | High20 uses \(t-1..t-20\) |
| `atr_period` | `ATR_PERIOD` | `14` | `int` | ATR14 (Wilder) |
| `volume_sma_period` | `VOLUME_SMA_PERIOD` | `20` | `int` | Volume SMA20 |
| `volume_ratio_min` | `volume_ratio_min` | `1.00` | `Decimal` | Backtest variant `1.20` is separate |
| `pullback_ema_tolerance` | `pullback_ema_tolerance` | `0.005` | `Decimal` | 0.5% tolerance |
| `stop_initial_atr_mult` | `stop_initial_atr_mult` | `2.5` | `Decimal` | Initial stop multiple |
| `trail_atr_mult` | `trail_atr_mult` | `3.0` | `Decimal` | Trailing stop multiple |

---

## Strategy warmup minimums (hard blocks)

**Code constants:** `services/strategy_engine/constants.py`  
**Spec section:** `docs/strategy-specification.md` §3.1

| Constant | Default | Meaning |
|---|---:|---|
| `MIN_DAILY_CANDLES` | `21` | Minimum closed daily candles |
| `MIN_WEEKLY_CANDLES` | `50` | Minimum closed weekly candles |
| `MIN_MONTHLY_CANDLES` | `20` | Minimum closed monthly candles |

---

## Risk Engine (RiskParameters)

Risk parameters are part of the **coupled V1 system** (strategy + risk) and are referenced by the strategy spec and reason codes.

**Code model:** `services/risk_engine/models.py::RiskParameters`  
**Default constants:** `services/risk_engine/constants.py`  
**Freeze validation:** `services/risk_engine/validation.py::validate_parameters`

| Parameter | Spec name | Default (Freeze 1.0) | Type | Freeze rule |
|---|---|---:|---|---|
| `risk_specification_version` | `RISK_SPECIFICATION_VERSION` | `1.0.0` | `str` | Must match risk spec header |
| `strategy_version` | `STRATEGY_VERSION` | `1.0.0` | `str` | Coupling guard |
| `risk_per_trade_pct` | `risk_per_trade_pct` | `0.005` | `Decimal` | **Must be >0 and ≤ frozen maximum** |
| `max_portfolio_risk_pct` | `max_portfolio_risk_pct` | `0.02` | `Decimal` | **Must be >0 and ≤ frozen maximum** |
| `max_open_positions` | `max_open_positions` | `3` | `int` | **Must be >0 and ≤ frozen maximum** |
| `max_leverage` | `max_leverage` | `2.0` | `Decimal` | **Must be >0 and ≤ frozen maximum** |
| `risk_rounding_tolerance` | `risk_rounding_tolerance` | `0.001` | `Decimal` | Must be finite and ≥0 |

---

## Paper trading config (execution guardrails)

These are not strategy parameters, but they are **production-shaped guardrails** that must not be casually changed.

**Config model:** `services/paper_trading/config.py::PaperTradingConfig`

| Setting | Env var | Default | Type | Notes |
|---|---|---:|---|---|
| `paper_initial_equity` | `PAPER_INITIAL_EQUITY` | `100000` | `Decimal` | Paper account equity |
| `paper_fee_rate` | `PAPER_FEE_RATE` | `0.0005` | `Decimal` | Fee model |
| `paper_slippage_bps` | `PAPER_SLIPPAGE_BPS` | `5` | `Decimal` | Slippage model |
| `paper_max_leverage` | `PAPER_MAX_LEVERAGE` | `2` | `Decimal` | Hard-capped at `≤ 2` |
| `evaluation_delay_seconds` | `PAPER_EVALUATION_DELAY_SECONDS` | `5` | `int` | Daily close eval jitter |
| `fill_delay_seconds` | `PAPER_FILL_DELAY_SECONDS` | `0` | `int` | Fill simulation delay |
| `kill_switch_close_policy` | `PAPER_KILL_SWITCH_CLOSE_POLICY` | `FREEZE` | `enum` | V1 supports `FREEZE` only |

