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

## Contract versions (#169 / #208)

| Constant | Version | Meaning |
|----------|---------|---------|
| `METRICS_SCHEMA_VERSION` | `1.2` | Current emit: `funding_costs` + gross identity; `benchmark_result` is **net**; requires `benchmark.gross_return`, `cost_model_version`, and parity flags true |
| `METRICS` legacy `1.1` | `1.1` | Funding identity; `benchmark_result` was **gross** (readable, not emitted) |
| `COST_MODEL_VERSION` | `1.1` | Documents assumed_rate-per-daily-candle semantics |

Legacy `1.0` / `1.1` artifacts remain readable where schema fields allow; new runs emit `1.2`.
Do not treat `1.0`, `1.1`, and `1.2` research results as the same contract.
