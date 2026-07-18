# Regime Behaviour and Transition Risk (P4.9)

**Status:** Implemented (generic Research Engine infrastructure)
**Issue:** [#289](https://github.com/Pain1234/save-money-trading-bot/issues/289)
**Package:** `services/research/regime_behaviour/`
**Depends on:** [#287](https://github.com/Pain1234/save-money-trading-bot/issues/287) `regime_metrics.json`,
[#285](https://github.com/Pain1234/save-money-trading-bot/issues/285) `regime_labels.json`
**Contract:** [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) Layer 4 + §5

## Purpose

Derive **deterministic** behaviour labels per regime and a separate
transition-risk profile. No LLM as source of persisted labels.

## Rules (policy `1.0`)

Versioned + content-hashed thresholds in `BehaviourPolicy`.

| Label | Deterministic condition (summary) |
|-------|-----------------------------------|
| `DEFENSIVE_INACTIVE` | Zero closed trades (incl. Sideways) — **not** a failure |
| `PROFITABLE` | `net_pnl >= profitable_net_min` |
| `CONTROLLED_BLEED` | Mild negative net within floor |
| `WHIPSAW_PRONE` | Many trades, non-positive expectancy, negative net |
| `COST_INTENSIVE` | Cost / max(\|net\|,1) above ratio |
| `TAIL_RISK_EXPOSED` | `tail_loss` above floor |
| `SHOCK_DEPENDENT` | High PnL concentration with losses |
| `LATE_ENTRY` / `LATE_EXIT` | Exposure proxies on trend regimes |
| `OVERACTIVE_REENTRY` | Very high trade count with non-positive net |
| `INSUFFICIENT_EVIDENCE` | Insufficient status / empty label set |

`main_weakness` / `main_strength` follow a documented priority order.

## Transition risk

From `regime_labels.transitions` + `day_events` (optional trades in IN/OUT
windows). Emits `risk_label` and counts; MAE / time-to-derisk stay
`NOT_AVAILABLE` until tick paths exist.

## Output

`behavior_profile.json` (runner-written):

- `llm_source: false`, `decision_binding: false`, `auto_promotion: false`
- `human_readable_summary: null` (optional prose never feeds labels)
- Per-regime `labels`, global weakness/strength, `transition_risk`

## Reproducibility

```text
python -m pytest tests/research/test_regime_behaviour.py -q
```

## Non-scope

Confidence (#288), Parameter area (#290), Scorecard API (#291), private V1 results.
