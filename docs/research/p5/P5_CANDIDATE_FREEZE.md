# P5 Candidate Freeze Manifest (planning template)

**Status:** PLANNING / UNSIGNED
**Issue:** [#196](https://github.com/Pain1234/save-money-trading-bot/issues/196) (P5-00)
**Rule:** After human freeze, no parameter change may keep the name Strategy V1 without a new `strategy_version`, new freeze manifest, and new validation chain.

## Identity (fill at freeze)

| Field | Value | Notes |
|-------|-------|-------|
| `strategy_id` | `trend_v1` (planned) | Matches resolver key in P4 docs |
| `strategy_version` | `1.0.0` (planned pin) | Must match code + spec |
| Git commit | TBD | Exact SHA at freeze |
| Strategy code hash | TBD | Hash of resolved strategy module tree |
| Freeze timestamp (UTC) | TBD | |
| Human approver | TBD | Required |
| Private storage path | TBD | Per #181 — not public `artifacts/` |

## Parameters (planned pin = Spec Freeze 1.0 / inventory)

Source: `docs/strategy-v1-parameter-inventory.md`, `docs/strategy-specification.md`.

| Parameter | Frozen value |
|-----------|--------------|
| `monthly_ema_period` | 20 |
| `weekly_ema_fast` | 20 |
| `weekly_ema_slow` | 50 |
| `daily_ema_period` | 20 |
| `breakout_lookback` | 20 |
| `atr_period` | 14 |
| `volume_sma_period` | 20 |
| `volume_ratio_min` | `1.00` (**not** the 1.20 backtest variant) |
| `pullback_ema_tolerance` | 0.005 |
| `stop_initial_atr_mult` | 2.5 |
| `trail_atr_mult` | 3.0 |

## Portfolio / risk (coupled Risk V1)

| Field | Frozen value |
|-------|--------------|
| Symbols | BTC, ETH, SOL |
| `risk_per_trade_pct` | 0.005 |
| `max_portfolio_risk_pct` | 0.02 |
| `max_open_positions` | 3 |
| `max_leverage` | 2.0 |
| `risk_rounding_tolerance` | 0.001 |
| Portfolio rules | Per risk + strategy specs (no discretionary overrides) |

## Rules references (not restated here)

| Concern | Source of truth |
|---------|-----------------|
| Entry rules | `docs/strategy-specification.md` |
| Exit rules | same |
| Stop rules | same |
| Candle timeframes | Daily evaluation; weekly/monthly filters per spec |
| Warmup minima | Daily ≥21, Weekly ≥50, Monthly ≥20 |

## Model / contract versions (pin at freeze)

| Contract | Planned version | Doc |
|----------|-----------------|-----|
| Cost model | `1.1` | `docs/research/FUNDING.md` / costs |
| Fee assumption | Spec `fee_assumption.model_version` | ExperimentSpec |
| Slippage model | Spec `slippage_assumption.model_version` | ExperimentSpec |
| Funding model | Spec `funding_assumption.model_version` | ExperimentSpec |
| Benchmark | versioned `benchmark_id@version` | METRICS / benchmark contract |
| Metrics schema | `1.1` | `docs/research/METRICS_DEFINITIONS.md` |
| Report schema | as emitted by research runner | ARTIFACT_FORMAT |
| Dataset contracts | P3 DatasetManifest + P4 bind | market-data + dataset_binding |
| Random seeds | TBD in protocol | Must be fixed before OOS |

## Freeze discipline

- After freeze: **no** silent edits to strategy code or parameters under this version.
- Any material change → bump `strategy_version`, new manifest, restart validation chain.
- Failed OOS must not be “fixed” by retuning V1 in place.

## Sign-off

| Role | Name | Date | Signature / issue comment |
|------|------|------|---------------------------|
| Preparer | TBD | TBD | |
| Human freeze approval | TBD | TBD | |

**Final holdout status at freeze:** must remain **unopened**.
