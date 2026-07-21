# P5 Benchmarks and Regimes

**Status at authoring:** CONTRACTS PROPOSED — awaiting human approval
**Lifecycle note:** This contract preserves authoring-time proposal and sign-off
fields. Current P5 phase and gate status is maintained only in
[P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md).
**Issue:** [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199) (P5-03)
**Symbols:** BTC, ETH, SOL only (no new assets).

## Benchmarks (versioned)

All benchmarks use the same evaluation period, DatasetManifest, quote currency (USD notionals as in research Spec), and starting capital as the candidate run.

| benchmark_id | version | Definition | Costs | Rebalance |
|--------------|---------|------------|-------|-----------|
| `cash_null` | `1.0` | Flat cash equity = start capital | none | n/a |
| `buy_and_hold_BTC` | `1.0` | P4 buy-and-hold on BTC daily closes; report **net** (`benchmark_result`) and **gross** (`BenchmarkRef.gross_return`) under metrics schema **1.2** | Spec fee/slippage/funding via execution primitives when `cost_parity=true` (parity ≠ zero costs; #208) | buy once at first close |
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

### Relationship to P4.9 scorecard classifier

P5-03 (#199) remains the **Strategy V1 evaluation contract** for monthly trend/vol
labels used in private P5 reporting. Generic, versioned Research Engine
classification (including explicit transitions and content-hashed
`classifier_version`) is implemented under P4.9 [#285](https://github.com/Pain1234/save-money-trading-bot/issues/285)
(`services/research/regime/`, docs: [`REGIME_CLASSIFIER.md`](../REGIME_CLASSIFIER.md))
and bound for Strategy V1 freeze via
[P5_SCORECARD_POLICY_BIND.md](P5_SCORECARD_POLICY_BIND.md) /
[#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)
(classifier `1.0` content hash pinned; Holdout remains closed; ADR-020).

Classifier `1.0` reuses the public +5% / −5% trend thresholds from this
document and adds a three-way vol axis (`LOW_VOL` / `NORMAL_VOL` / `HIGH_VOL`)
with **generic public absolute bounds** (not the private partition-B median).
Do **not** treat the private median overlay as a second scorecard taxonomy.
Scorecard evidence uses classifier `1.0` only; keep determinism and freeze
before final holdout. See
[`docs/research/REGIME_SCORECARD.md`](../REGIME_SCORECARD.md).

**Engine implementation (`classifier_version` `1.0`, Issue #285):**

| Axis | Scorecard SoT (classifier `1.0` / #294) | #199 private overlay only |
|------|------------------------------------------|----------------------------|
| Trend | Same ±5% calendar-month return on closed daily closes | Same |
| Vol | Three-way `LOW_VOL` / `NORMAL_VOL` / `HIGH_VOL` via **versioned absolute** daily-return stdev thresholds (`vol_low_max=0.015`, `vol_high_min=0.035`) | Binary high/low vs **private** partition-B median (not in public repo; not scorecard cells) |
| Transitions | Directed ids + day-level `TRANSITION_IN` / `OUT` / `STABLE_REGIME` windows | Optional in private reports |
| Artifact | Run sidecar `regime_labels.json` (dataset + classifier + bars hashes) | Private economic tables stay out of public fixtures |

Public `1.0` vol thresholds are infrastructure defaults and, under
[#294](https://github.com/Pain1234/save-money-trading-bot/issues/294) /
[P5_SCORECARD_POLICY_BIND.md](P5_SCORECARD_POLICY_BIND.md) (ADR-020), are the
**sole SoT for scorecard / Research Engine regime evidence**. The private
partition-B median High/Low rule remains a **private diagnostic overlay only**
— not a substitute for classifier `1.0` cells. A median-based scorecard axis
requires a new classifier version + new freeze. See also
[`REGIME_CLASSIFIER.md`](../REGIME_CLASSIFIER.md).

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
