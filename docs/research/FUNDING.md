# Funding semantics (P4 / #164)

## Binding rules

| Spec / model | Behavior |
|--------------|----------|
| `funding_assumption.enabled=false` | No funding applied. `funding_costs` / `total_funding` = 0. Bundle events ignored. |
| `enabled=true` | `assumed_rate` **required** (research Spec fail-closed via `require_cost_fields`). |
| `FundingModel.assumed_rate` set | Applied **once per daily candle** while a position is open. Bundle `FundingEvent`s are **ignored**. |
| `FundingModel.enabled` + `assumed_rate=None` | Legacy/backtester path: apply matching `FundingEvent`s from the bundle whose timestamps fall inside the candle window. |

Positive rate → long pays (cash decreases). Negative rate → long receives.

## Gross / net identity

```text
gross_pnl = net_pnl + fees + slippage_costs + funding_costs
```

`funding_costs` is machine-readable on `metrics.json` and listed in `report.md`.
`costs.json` records `funding_assumed_rate`, `funding_semantics`, and the gross identity string.
