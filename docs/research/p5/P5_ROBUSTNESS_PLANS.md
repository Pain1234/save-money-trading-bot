# P5 Robustness execution plans

**Status:** Public helpers land one issue at a time (#200–#203)
**This PR:** #200 walk-forward only

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

## Later issues

- #201 cost stress — `cost_stress.py`
- #202 parameter neighborhood — `parameter_stability.py`
- #203 path bootstrap — `bootstrap.py`

## Explicit non-execution here

No private economic tables. Holdout C remains sealed.
