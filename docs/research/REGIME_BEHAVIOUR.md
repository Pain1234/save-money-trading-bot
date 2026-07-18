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

Versioned + content-hashed thresholds **and** priority orders in
`BehaviourPolicy` (including late-entry/exit floors, reentry multiplier,
transition-risk cutoffs). Silent edits change `policy_content_hash`.

| Label | Deterministic condition (summary) |
|-------|-----------------------------------|
| `DEFENSIVE_INACTIVE` | Zero closed trades **and** trend `SIDEWAYS` — not a failure |
| `LATE_ENTRY` | Zero closed trades on `BULL`/`BEAR`, or low time-in-market on trend |
| `PROFITABLE` | `net_pnl >= profitable_net_min` (`0.01`; break-even / missing ≠ profit) |
| `CONTROLLED_BLEED` | Mild negative net within floor |
| `WHIPSAW_PRONE` | Many trades, non-positive expectancy, negative net |
| `COST_INTENSIVE` | Cost / max(\|net\|,1) above ratio |
| `TAIL_RISK_EXPOSED` | `tail_loss` above floor |
| `SHOCK_DEPENDENT` | High PnL concentration with losses |
| `LATE_EXIT` | High time-in-market on trend with negative net |
| `OVERACTIVE_REENTRY` | Trades ≥ whipsaw × multiplier with non-positive net |
| `INSUFFICIENT_EVIDENCE` | Missing required metrics, untrusted evidence, or empty label set |

`main_weakness` / `main_strength` use **policy-versioned** priority tuples.

### Evidence fail-closed

Only explicit `evidence_status == "OK"` is trusted. Missing or unknown status
is treated as untrusted (`evidence_status` recorded as `MISSING` when absent).

When evidence is untrusted (e.g. incomplete coverage from #287 →
`INCONCLUSIVE`, or missing status):

- Per-regime labels forced to `INSUFFICIENT_EVIDENCE`
- `main_strength` suppressed (`null`)
- `evidence_trusted: false`
- Transition `risk_label` → `INSUFFICIENT_EVIDENCE`

Missing / `NOT_AVAILABLE` `net_pnl` on active regimes → `INSUFFICIENT_EVIDENCE`
(never coerced to 0 / PROFITABLE).

## Identity

`behaviour_id` binds: `run_id`, `quality_id`, `classification_id`,
`classifier_content_hash`, `transition_evidence_hash` (canonical transitions +
day_events + trade fields that drive window PnL/costs/turnover),
`policy_version`, `policy_content_hash`.

Metrics **must** carry `dataset_id` and `dataset_content_hash`. Pin checks
against `regime_labels` require exact match on dataset **and** classification
pins (no empty-left skip; reject foreign classification of the same dataset).

`evaluate_behaviour_profile_from_run_dir` **requires** external
`trusted_checksums` (registry trust anchor). Local `checksums.json` alone is
not accepted.

## Transition risk

From `regime_labels.transitions` + `day_events` (optional trades in IN/OUT
windows). Emits `risk_label`, trade count, PnL, costs, and
`window_turnover` (`quantity × entry_fill_price`). MAE / time-to-derisk stay
`NOT_AVAILABLE` until tick paths exist.

## Output

`behavior_profile.json` (runner-written):

- `llm_source: false`, `decision_binding: false`, `auto_promotion: false`
- `human_readable_summary: null` (optional prose never feeds labels)
- Per-regime `labels`, global weakness/strength, `transition_risk`
- `evidence_trusted`, classification pins, `transition_evidence_hash`

## Reproducibility

```text
python -m pytest tests/research/test_regime_behaviour.py -q
```

## Non-scope

Confidence (#288), Parameter area (#290), Scorecard API (#291), private V1 results.
