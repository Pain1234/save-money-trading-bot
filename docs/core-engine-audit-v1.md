# Core Engine Audit V1 — Remediation Report

**Date:** 2026-07-11  
**Scope:** Strategy Engine V1.0, Risk Engine V1.0, Backtester V1.0  
**Frozen specs:** unchanged (`docs/strategy-specification.md`, `docs/risk-specification.md`, `docs/product-specification.md`)

---

## Executive Decision: Perpetual Margin Accounting

The backtester now uses **perpetual margin accounting** instead of a hybrid spot model where full entry notional was debited from cash.

| Concept | V1 behavior |
|---------|-------------|
| Wallet (`cash` / `wallet_balance_usd`) | Fees, funding, realized PnL only |
| Used margin | Σ (fill notional / max_leverage) |
| Unrealized PnL | Σ qty × (mark − entry fill) |
| Equity | Wallet + unrealized PnL |
| Entry | Wallet − entry fee; margin reserved on position |
| Exit | Wallet += gross PnL − exit fee; margin released |

The field `PortfolioState.cash` is documented as **wallet balance**, not free spot purchase power.

---

## Findings — Status

### Blockers / Critical (fixed)

| ID | Issue | Resolution |
|----|-------|------------|
| **B1** | Spot-style full-notional cash debit on entry | Perpetual accounting in `portfolio.py`, `engine.py`, `models.py` |
| **C1** | Same-day close used as mark at open fill (look-ahead) | `resolve_marks_at_open()` — open or prior close only |
| **C2** | Risk evaluated before slippage with signal stop | Fill order: slippage → fill-based stop → `RiskEngine.evaluate` |
| **C3** | Actual trade risk could exceed budget after fill | Post-fill risk; gap up/down tests assert risk ≤ budget |

### Major (fixed or documented)

| ID | Issue | Resolution |
|----|-------|------------|
| **M1** | Intent ID marked processed before terminal decision | `OrderStatus` lifecycle; `processed_intent_ids` updated only on FILLED/REJECTED |
| **M2** | Rejection records contained `RC_RISK_APPROVED` | Strip approval code; use actual reject reason codes |
| **M3** | `trail_stop > entry_price` flagged as corrupt | **Rejected audit finding** — valid for profitable longs; open risk may be zero; **no code change** |
| **M4** | Portfolio gate vs leverage reduction ordering | **Deferred** — current reduction is conservative, no over-risk |
| **M5** | Fixed warmup candle counts | `min_candles_for_warmup(timeframe, params)` from configured periods |
| **M6** | Undefined indicators emitted `RC_REJECT_DATA` | Now `RC_REJECT_WARMUP` when indicators undefined due to insufficient history |

---

## M3 — Rejected Audit Finding

**Original concern:** Trailing stop above entry price indicates corrupted state.

**Decision:** For profitable long positions, `trail_stop > entry_price` is **valid**. Open risk may correctly be zero. Risk Engine behavior unchanged per product decision.

---

## M4 — Specification Gap (deferred)

Portfolio gate and leverage-reduction ordering may differ from a strict reading of the risk spec. Current implementation reduces quantity conservatively and does **not** increase capital at risk. Documented as open specification question; no behavioral change in V1.

---

## Remaining Model Assumptions (V1)

1. **Funding notional** = quantity × entry fill price (not mark price).
2. **Margin** = notional / max_leverage (no cross/isolated modes, no maintenance margin).
3. **Daily-bar** stop resolution; intrabar assumption `ENTRY_AT_OPEN_THEN_STOP_SAME_CANDLE`.
4. **Trailing updates** use daily **close**, not intrabar high.
5. **EOD equity marks** use daily close.
6. **Open-fill marks** use bar open or prior close (never same-day close).

---

## Remaining Specification Gaps

- M4 portfolio gate ordering vs leverage reduction sequence.
- Funding event schedule vs exchange 8h cadence (bundle-driven in backtester).
- Tick-level execution and liquidation (out of V1 scope).
- Hyperliquid cross-margin, funding on mark, and order-book dynamics.

---

## New Independent Regression Tests

### Perpetual accounting (`tests/backtester/test_backtest_perpetual_accounting.py`)

- Entry wallet deducts fee only; margin reserved correctly
- Equity unchanged without price move
- Unrealized PnL on rise/decline (unit)
- Exit at entry (gross PnL = 0) net of fees/funding
- Winning / losing trade wallet paths
- Two positions at 2× leverage

### Look-ahead marks (`tests/backtester/test_backtest_marks_at_open.py`)

- `resolve_marks_at_open()` uses open or prior close, not same-day close

### Fill-based risk (`tests/backtester/test_backtest_fill_risk.py`)

- Gap down / gap up: `initial_risk_usd ≤ equity × risk_per_trade_pct`
- Fill stop matches position initial stop

### Intrabar (`tests/backtester/test_backtest_intrabar.py`)

- Same-candle low triggers initial stop after open fill
- Same-candle high does not raise trailing stop before EOD close update

### Intent lifecycle (`tests/backtester/test_backtest_intent_lifecycle.py`)

- Rejected intents exclude `RC_RISK_APPROVED` as sole reason
- Filled intents in `processed_intent_ids`
- Duplicate intent blocked via `initial_processed_intent_ids`

### End-to-end reference (`tests/backtester/test_backtest_e2e_reference.py`)

- No mocks for `StrategyEngine.evaluate` or `RiskEngine.evaluate`
- Hand-constructed daily/weekly/monthly candles → real LONG_ENTRY → fill → stop
- End equity, fees, PnL, R-multiple vs hand-computed reference

### Strategy warmup (`tests/strategy_engine/test_validation.py`)

- `min_candles_for_warmup` derives from `StrategyParameters`

---

## Validation Results (2026-07-11)

```
pytest tests/strategy_engine tests/risk_engine tests/backtester -q
182 passed

mypy services/strategy_engine services/risk_engine services/backtester
Success: no issues found in 27 source files

ruff check services/strategy_engine services/risk_engine services/backtester \
  tests/strategy_engine tests/risk_engine tests/backtester
All checks passed (pre-existing E501 in tests/strategy_engine/conftest.py, test_entry.py documented)
```

| Suite | Tests |
|-------|-------|
| strategy_engine | 51 |
| risk_engine | 50 |
| backtester | 81 |
| **Total** | **182** |

---

## Known Differences vs Hyperliquid

- Wallet + reserved margin model (not on-chain collateral semantics).
- Funding charged on entry notional, not mark.
- No partial fills, order book, funding rate API, or liquidation engine.
- Daily-bar execution granularity.
- Conservative intrabar ordering for entries and stops.

---

## Files Changed (remediation)

- `services/backtester/engine.py` — perpetual accounting, fill-risk order, intent lifecycle, marks
- `services/backtester/portfolio.py` — `resolve_marks_at_open`, margin/PnL helpers
- `services/backtester/models.py` — `margin_reserved`, wallet documentation, `OrderStatus`
- `services/strategy_engine/validation.py` — parameter-aware warmup
- `services/strategy_engine/engine.py` — `RC_REJECT_WARMUP` for undefined indicators
- `services/backtester/README.md` — perpetual model documentation
- `tests/backtester/test_backtest_*.py` — new regression and E2E tests
- `tests/strategy_engine/test_validation.py` — warmup parameter test

---

FREIGEGEBEN FÜR PAPER TRADING
