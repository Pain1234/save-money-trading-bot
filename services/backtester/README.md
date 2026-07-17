# Backtester V1.0

Deterministic event-driven backtester for **Strategy Engine V1.0** and **Risk Engine V1.0**.

The backtester delegates all signal, stop, sizing, and portfolio-risk logic to the frozen engines. It only simulates execution, fees, slippage, funding, and portfolio accounting.

## Architecture

| Component | Role |
|-----------|------|
| `BacktestConfig` | Symbols (ordered), capital, engine params, fee/slippage/funding models |
| `HistoricalDataBundle` | Daily/weekly/monthly candles + optional funding series |
| `BacktestEngine` | Main event loop |
| `PendingIntent` | Queued entry after strategy signal (filled next open) |
| `SimulatedPosition` / `PortfolioState` | Open positions, wallet balance, reserved margin |
| `BacktestTrade` | Closed trade record with full audit trail |
| `BacktestResult` | Trades, equity curve, metrics, evaluations, rejections |

## Event Order (per daily bar)

For each UTC daily candle `t` (symbols processed in `BacktestConfig.symbols` order):

1. **Fill pending entries** at `Open[t]` with slippage, fill-based initial stop, then **RiskEngine.evaluate**
2. **Same-candle stop check** on newly filled positions (conservative intrabar)
3. **Stop exits** on remaining open positions (gap at open, else effective stop)
4. **Funding** (if enabled) for events within the candle while position is open
5. **Strategy evaluation** at daily close + 5s
6. **Queue pending intents** for `LONG_ENTRY` signals
7. **Trailing stop update** (Strategy Engine 8-step sequence, uses close only)
8. **Equity snapshot** at close (wallet + unrealized PnL)

## Entry Execution Model

- Signal generated after close of candle `t` (evaluation at `close_time + 5s`)
- Order prepared for next available daily open
- Fill at `Open[t+1]` with entry slippage (long: price worsens upward)
- **Risk evaluation after slippage** using actual fill price and fill-based initial stop
- Entry fee deducted from **wallet balance** only (full notional is not subtracted)
- Reserved margin = fill notional / max_leverage
- **No fill at signal close price**

## Perpetual Margin Accounting

V1 uses a simplified perpetual margin model (not spot purchase):

| Field | Meaning |
|-------|---------|
| `PortfolioState.cash` / `wallet_balance_usd` | Wallet balance after fees, funding, realized PnL |
| `margin_reserved` (per position) | Fill notional / effective leverage |
| `used_margin_usd` | Sum of reserved margin across open positions |
| `unrealized_pnl_usd` | Σ quantity × (mark − entry fill) |
| `equity_usd` | Wallet + unrealized PnL |
| `available_margin_usd` | Equity − used margin |

**Entry:** wallet − entry fee; margin reserved on position.

**During position:** unrealized PnL marks wallet equity; funding debits wallet once per event.

**Exit:** wallet += gross PnL − exit fee; margin released; trade `net_pnl` includes funding for reporting without double-charging wallet.

Open-fill marks use `resolve_marks_at_open()` — bar open or prior close, never same-day close (look-ahead safe).

## Stop Execution Model

For long positions on candle `t`:

1. If `Open[t] < EffectiveStop` → exit at `Open[t]`, reason `RC_EXIT_STOP_GAP`
2. Else if `Low[t] <= EffectiveStop` → exit at `EffectiveStop`
3. Else position remains open

Exit slippage worsens the exit price (long: downward). Exit fee on actual fill notional.

Trailing stops use `update_trailing_stop()` from Strategy Engine — stops never decrease.

**Weekly trend break** does not auto-exit; it only blocks new entries via strategy evaluation.

## Intrabar Assumption

When entry fill and stop trigger occur on the same candle:

**`ENTRY_AT_OPEN_THEN_STOP_SAME_CANDLE`**

After entry fills at open, stop logic runs on the same candle. This is conservative for longs (never assumes favorable intrabar ordering).

## Fees

Configurable `entry_fee_rate` and `exit_fee_rate`. Applied to actual fill notional. Reduce cash and appear in trade records and aggregate metrics.

## Slippage

Configurable `slippage_bps`:

- Entry: `fill = reference × (1 + bps/10000)`
- Exit: `fill = reference × (1 - bps/10000)`

No positive slippage in favor of the strategy.

## Funding

- Disabled by default (`funding_enabled = false` / `FundingModel.enabled = false`)
- When enabled **with** `FundingModel.assumed_rate`: apply that constant rate **once
  per daily candle** while a position is open (research path). Bundle
  `FundingEvent`s are ignored in this mode.
- When enabled **without** `assumed_rate`: apply matching `FundingEvent`s from the
  bundle whose timestamps fall inside the candle window (legacy/event path).
- No future funding values; notional = quantity × entry price
- All payments recorded per trade and in `total_funding`

See also `docs/research/FUNDING.md`.

## Multi-Asset Sorting

Symbol processing order is **explicit** via `BacktestConfig.symbols`. Default: `BTC, ETH, SOL`.

Risk engine receives updated portfolio state between symbols at the same timestamp.

## Duplicate Protection

`client_intent_id = symbol:strategy_version:timestamp:entry_type` (deterministic, no randomness).

Processed intent IDs are tracked only after a **terminal** decision (`FILLED` or `REJECTED`). Rejected intents are not burned before risk evaluation completes.

## Look-Ahead Protection

- UTC only; no system clock in calculations
- Only closed candles (`is_closed=True`, `close_time <= as_of`)
- Weekly/monthly filtered to completed candles as of evaluation time
- No future funding events
- **Open-fill marks:** current bar open or last known close — never same-day close

## Metrics

Total return, CAGR, max drawdown, win rate, profit factor, expectancy (USD and R), streaks, Sharpe, Sortino, time in market, per-symbol and per-entry-type breakdown. Division by zero returns `None` (not infinity).

## Known Differences vs Hyperliquid

- Perpetual margin model: wallet + reserved margin (not full notional cash debit)
- Simplified margin: notional / max_leverage (no cross/isolated modes)
- Funding uses entry notional, not mark price (V1 model assumption)
- No partial fills, order book, or liquidation engine
- Daily-bar stop resolution (not tick-level)
- No funding outside configured event timestamps
- M4 portfolio gate ordering deferred (conservative leverage reduction)

## Example

```python
from decimal import Decimal
from backtester import BacktestEngine, BacktestConfig, HistoricalDataBundle
from risk_engine.models import SymbolConstraints

constraints = {
    "BTC": SymbolConstraints(
        quantity_step=Decimal("0.001"),
        minimum_quantity=Decimal("0.001"),
        minimum_notional=Decimal("10"),
        price_tick_size=Decimal("0.01"),
    ),
}

config = BacktestConfig(
    symbols=("BTC",),
    initial_cash=Decimal("100000"),
    symbol_constraints=constraints,
)

bundle = HistoricalDataBundle(
    daily={"BTC": daily_candles},
    weekly={"BTC": weekly_candles},
    monthly={"BTC": monthly_candles},
)

result = BacktestEngine().run(bundle, config)
print(result.metrics.total_return_pct, result.metrics.trade_count)
```

## Tests

```bash
pytest tests/strategy_engine tests/risk_engine tests/backtester -q
mypy services/strategy_engine services/risk_engine services/backtester
ruff check services tests
```

## Model Assumptions

1. Perpetual margin accounting (wallet balance ≠ spot purchase power)
2. Entry at next daily open after signal; risk after slippage and fill-based stop
3. Intrabar: entry at open, then stop check same candle; trailing uses close only
4. Funding notional = entry price × quantity (V1)
5. Mark price for EOD equity = daily close
6. One position per symbol maximum

## Open Specification Questions

- Exact intrabar priority when limit orders exist (N/A in V1 — market at open only)
- Funding event granularity vs exchange 8h schedule (configurable timestamps in bundle)
- M4: portfolio gate vs leverage reduction ordering (deferred; current behavior is conservative)
