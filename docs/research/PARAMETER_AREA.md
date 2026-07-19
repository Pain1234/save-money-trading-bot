# Parameter Area / Plateau Stability (P4.9)

**Status:** Implemented (generic Research Engine infrastructure)
**Issue:** [#290](https://github.com/Pain1234/save-money-trading-bot/issues/290)
**Package:** `services/research/parameter_area/`
**Depends on:** [#247](https://github.com/Pain1234/save-money-trading-bot/issues/247) sealed
`parameter_stability` robustness manifests
**Contract:** [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) §4 + Layer 5

## Purpose

Classify whether a **contiguous neighbourhood** of parameters remains stable
around the frozen point — not pick a new optimum. No automatic parameter
selection. No OOS/holdout plateau construction.

## Classification (policy `1.0`)

| Label | Meaning (summary) |
|-------|-------------------|
| `BROAD_STABLE_PLATEAU` | Large contiguous stable region + high stable share + gate-pass share |
| `NARROW_STABLE_AREA` | Smaller contiguous region / missing gates block BROAD |
| `ISOLATED_PEAK` | Frozen stable without stable OAT neighbors |
| `UNSTABLE` | No stable region / weak share / steep drop without plateau |
| `INSUFFICIENT_EVIDENCE` | Too few complete neighbors |

**Stable neighbor** (fail-closed): `status=complete`, `net_pnl` present and
≥ floor, **costs present** and within `max_cost_ratio`, optional gate when
`require_gate_for_stable`. Profit alone is never enough.

**Positive share** (stats only): strict `net_pnl > 0` (break-even is not positive).

**Contiguity:** adjacent steps on a single OAT axis **including the frozen
point**. Plateau size ignores stable runs that do not contain frozen.
BROAD/NARROW require `frozen_stable` and `plateau.includes_frozen`.

## Trust

`evaluate_parameter_area_from_robustness` requires:

- external `trusted_manifest_hash` (job/registry pin)
- `ExperimentRegistry` with `show(verify=True)` for base + child runs
- frozen parameters from sealed base-run `experiment.json`
- costs + gate_pass from sealed child `metrics.json` (gate = `net_pnl >= 0`,
  same as #248 `parameter_neighbor_pass_ratio`)

Direct `evaluate_parameter_area` is for fixtures/tests and **always** sets
`evidence_trusted=false` (no trust-bypass kwargs). Frozen observation
parameters must match `frozen_parameters` exactly, including `strategy_id`.

## Output

`parameter_area.json` (post-hoc; not required on every `run_experiment`):

- `frozen_point.unchanged=true`, `auto_parameter_selection=false`
- `oos_holdout_used=false`
- `decision_binding=false`, `auto_promotion=false`
- Stats: share positive / stable / gate-pass, median, dispersion, steepest drop
- Plateau size + contiguous region + `isolated_optimum`
- `parameter_area_id` binds `robustness_id` + policy + evidence hash

## API

```python
from research.parameter_area import (
    NeighborObservation,
    evaluate_parameter_area,
    evaluate_parameter_area_from_robustness,
    write_parameter_area_artifact,
)
```

## Reproducibility

```text
python -m pytest tests/research/test_parameter_area.py -q
```

## Non-scope

Scorecard API (#291), dashboard (#292), auto retune, private Strategy V1 results.
