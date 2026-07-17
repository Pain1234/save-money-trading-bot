# P5 Robustness execution plans

**Status:** Public helpers land one issue at a time (#200–#203)
**This PR:** #203 bootstrap (framework complete)

## #200 Walk-forward

| Module | Role |
|--------|------|
| `services/research/walk_forward.py` | Chronological folds; label embargo is separate from completed-monthly feature warmup |

Tests: `tests/research/test_p5_walk_forward.py`.

- Use `plan_walk_forward_folds` with `n_folds>=3`, `embargo_days=90` (or human-approved), and `feature_warmup_monthly_bars=20` (default).
- Feature context must contain >=20 **fully completed** calendar months (`count_completed_monthly_candles`); partial edge months do not count.
- Label context ends before the embargo window; feature context may include embargo calendar days for indicators.
- Identical frozen Spec params/costs every fold.
- Store per-fold + aggregate privately; do not drop failed folds.

## #201 Cost stress

| Module | Role |
|--------|------|
| `services/research/cost_stress.py` | Pre-registered stress scenario definitions |

Tests: `tests/research/test_p5_cost_stress.py`.

- Run `default_p5_cost_stress_scenarios(...)` with **base fee, slippage, and funding taken from the frozen Spec** (`funding off unless Spec enables`).
- Report gross/net; no scenario shopping after results.
- `combined_elevated` survival is required for ACCEPT (see decision rules).

## #202 Parameter stability

| Module | Role |
|--------|------|
| `services/research/parameter_stability.py` | Small symmetric neighborhoods |

Tests: `tests/research/test_p5_parameter_stability.py`.

- `symmetric_neighborhood` around freeze; diagnostic plots/tables private.
- Fragility gate: >= ceil(0.5*N) neighbors net>=0 on B (decision rules).
- Neighbor success cannot rescue failed freeze candidate.

## #203 Bootstrap / MC

| Module | Role |
|--------|------|
| `services/research/bootstrap.py` | Block bootstrap path net-PnL + max-drawdown quantiles |

Tests: `tests/research/test_p5_bootstrap.py`.

- Default proposal: block length 5 on daily net PnL increments; `n_simulations=1000`; `seed=42`.
- Use `block_bootstrap_paths` for Accept evidence (path net-PnL + max-drawdown quantiles).
- `block_bootstrap_means` is diagnostic only; it does **not** satisfy the 5% net-PnL Accept rule.
- Prefer block bootstrap; avoid IID shuffle of daily returns.
- Small-n / `block_length >= len(series)` / single-point series: helper **raises**; callers must document N/A (no false-confidence quantiles).

## Explicit non-execution here

No private economic tables. Holdout C remains sealed.
