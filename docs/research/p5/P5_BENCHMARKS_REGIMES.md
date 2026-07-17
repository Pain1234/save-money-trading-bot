# P5 Benchmarks and Regimes

**Status:** CONTRACTS PROPOSED — awaiting human approval
**Issue:** [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199) (P5-03)
**Symbols:** BTC, ETH, SOL only (no new assets).

## Benchmarks (versioned)

All benchmarks use the same evaluation period, DatasetManifest, quote currency (USD notionals as in research Spec), and starting capital as the candidate run.

| benchmark_id | version | Definition | Costs | Rebalance |
|--------------|---------|------------|-------|-----------|
| `cash_null` | `1.0` | Flat cash equity = start capital | none | n/a |
| `buy_and_hold_BTC` | `1.0` | P4 buy-and-hold on BTC daily closes | trading costs = 0 by P4 definition; `cost_parity=true` declares that | buy once at first close |
| `buy_and_hold_ETH` | `1.0` | same for ETH | same | same |
| `buy_and_hold_SOL` | `1.0` | same for SOL | same | same |
| `eq_weight_btc_eth_sol` | `1.0` | 1/3 notional each at period start; **monthly** calendar rebalance to 1/3 using closes | apply Spec base fee+slippage on rebalance turns only; funding off unless Spec enables | monthly |

Primary **informational** portfolio reference for reports: `eq_weight_btc_eth_sol@1.0`.
Hard ACCEPT gates use cash/net and drawdown per [P5_DECISION_RULES.md](P5_DECISION_RULES.md).

## Regime classifier (deterministic, pre-registered)

Classify each **calendar month** in the evaluation window using BTC daily closes in the same dataset:

1. **Trend:** month return \(r = P_{end}/P_{start} - 1\).
   - Bull if \(r ≥ +5%\)
   - Bear if \(r ≤ −5%\)
   - Sideways otherwise
2. **Volatility:** realized daily-return stdev within the month.
   - High vol if stdev ≥ median monthly stdev computed on partition B only (fixed at protocol freeze; store value privately)
   - Low vol otherwise

Each OOS/trade day inherits its month’s (trend, vol) labels.
**Forbidden:** dropping failed regimes after seeing results; selecting only winning regimes to rescue a failed aggregate.

## Symbol and portfolio reporting

Always report:

- Per-symbol contribution (net PnL, trades, max DD contribution)
- Combined portfolio (frozen risk limits)
- Regime breakdown tables (private)
- Correlation of symbol contributions (private)

## Sign-off

| Role | Name | Date |
|------|------|------|
| Author | Cursor agent (P5 execution) | 2026-07-17 |
| Human approver | **REQUIRED** on #199 | |

**No new assets. No post-hoc regime selection.**
