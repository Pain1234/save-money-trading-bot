# Regime Quality Metrics (P4.9)

**Status:** Implemented (generic Research Engine infrastructure)
**Issue:** [#287](https://github.com/Pain1234/save-money-trading-bot/issues/287)
**Package:** `services/research/regime_quality/`
**Depends on:** [#285](https://github.com/Pain1234/save-money-trading-bot/issues/285) `regime_labels.json`
**Contract:** [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) Layer 2

## Purpose

Compute **raw per-regime metrics** and an optional versioned quality **summary**
from a sealed research run. Worst- / strongest-regime profiles are derived from
raw net PnL — never from the summary score alone.

This module does **not**:

- Decide accept/reject
- Auto-promote strategies
- Encode private Strategy V1 thresholds
- Replace gates (#248) or validation studies (#249)

## Inputs (join)

| Artifact | Role |
|----------|------|
| `regime_labels.json` | Ex-post day/period labels (`point_in_time_safe=false`) |
| `trades.json` | PnL, costs, trade stats (attributed by **exit_time** UTC date) |
| `equity.json` | Drawdown / time-in-market (attributed by **time** UTC date) |
| `run_manifest.json` | `run_id`, `experiment_id`, dataset pins |

## Output

`regime_metrics.json` (also written by the research runner):

- Pins: experiment/run/dataset/classification/classifier hashes
- `regimes[]`: raw metrics per `trend|vol` cell + optional `quality_summary`
- `portfolio` / `symbols` views
- `worst_regime` / `strongest_regime`
- `decision_binding: false`, `auto_promotion: false`

Missing analytics → `NOT_AVAILABLE` (never coerced to `0`).
Zero-activity regimes → `status: ZERO_ACTIVITY` with zero trades/PnL; summary
score stays `NOT_AVAILABLE`.

## Score policy `1.0`

Illustrative public weights only (`weight_net_pnl` / `weight_drawdown` /
`weight_trade_count`), content-hashed. Summary never replaces raw metrics.

## Reproducibility

```text
python -m pytest tests/research/test_regime_quality.py \
  tests/research/test_runner_registry.py -q
```

## Non-scope

- Confidence (#288), Behaviour (#289), Parameter area (#290), Scorecard API (#291)
