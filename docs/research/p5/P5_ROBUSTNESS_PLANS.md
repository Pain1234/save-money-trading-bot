# P5 Robustness execution plans (#200–#203)

**Status:** FRAMEWORK LANDED (public helpers) — private economic runs await human freezes + partition B data
**Issues:** #200, #201, #202, #203

## Public infrastructure

| Module | Role |
|--------|------|
| `services/research/walk_forward.py` | Chronological folds; **label embargo** ≠ **feature warmup** (#200) |
| `services/research/cost_stress.py` | Pre-registered stress scenario definitions (#201) |
| `services/research/parameter_stability.py` | Small symmetric neighborhoods (#202) |
| `services/research/bootstrap.py` | Block bootstrap **path** net-PnL + max-drawdown quantiles (#203) |

Tests: `tests/research/test_p5_robustness_helpers.py`.

## Private execution (after freezes)

All numeric outputs go to `Pain1234/save-money-trading-bot-private-research` under `artifacts/research/`. Public issues get status checklists only.

### #200 Walk-forward

- Use `plan_walk_forward_folds` with `n_folds≥3`, `embargo_days=90` (or human-approved), and `feature_warmup_days=DEFAULT_FEATURE_WARMUP_DAYS_MONTHLY_EMA_20` (620) unless human overrides with justification.
- Feature context must be non-empty and span warmup; label context ends before the embargo window.
- Identical frozen Spec params/costs every fold.
- Store per-fold + aggregate privately; do not drop failed folds.

### #201 Cost stress

- Run `default_p5_cost_stress_scenarios()` on partition B (and later OOS only under frozen set).
- Report gross/net; no scenario shopping after results.
- `combined_elevated` survival is required for ACCEPT (see decision rules).

### #202 Parameter stability

- `symmetric_neighborhood` around freeze; diagnostic plots/tables private.
- Fragility gate: ≥ ceil(0.5×N) neighbors net≥0 on B (decision rules).
- Neighbor success cannot rescue failed freeze candidate.

### #203 Bootstrap / MC

- Default proposal: block length 5 on daily **net PnL increment** series; `n_simulations=1000`; `seed=42`.
- Use `block_bootstrap_paths` for Accept evidence (path net-PnL quantiles + max-drawdown quantiles).
- `block_bootstrap_means` is diagnostic only; it does **not** satisfy the 5% net-PnL Accept rule.
- Prefer block bootstrap; avoid IID shuffle of daily returns.
- Small-n → document N/A rather than false confidence.

## Explicit non-execution here

No private economic tables are written by this public PR. Holdout C remains sealed.
