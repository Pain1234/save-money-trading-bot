# Evidence Confidence Profile (Issue #288 / P4.9 Layer 3)

Derives scorecard **evidence confidence** from measurable research inputs only.
Quality scores (#287) and confidence stay separate. This module does **not**:

- accept a free-form / manual confidence override
- invent PSR / DSR / PBO / MTRL (deferred to a follow-up when formula + tests exist)
- write to the gate registry or auto-promote paper/live
- hard-code private Strategy V1 / P5 thresholds

Contract parent: [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) § Layer 3.
Integrity gating context: [`GATES.md`](GATES.md) / #286
(`quality_scores_permitted` remains independent; `INVALID` integrity forces
confidence overall `NOT_AVAILABLE`).

## Labels

| Label | Meaning |
|-------|---------|
| `HIGH` | Strong measurable support under policy floors |
| `MEDIUM` | Adequate but limited |
| `LOW` | Weak support |
| `INSUFFICIENT` | Below documented floors (evidence present) |
| `NOT_AVAILABLE` | Required inputs missing (never coerced to `0` / PASS) |

## Policy versioning

`research.confidence.policy.ConfidencePolicy` is versioned data with a content
hash (`compute_confidence_policy_content_hash`). Policy `1.0` floors are generic
public examples (aligned with gate `min_closed_trades=10`). Frozen pin:

`CONFIDENCE_POLICY_1_0_CONTENT_HASH` in `services/research/confidence/policy.py`.

Extend by adding a **new** version; never mutate `1.0` in place.

## Dimensions (policy 1.0)

| Dimension | Required | Primary input |
|-----------|----------|---------------|
| `trade_sample` | yes | `closed_trades` |
| `time_coverage` | no | `equity_periods` (`len(equity)-1`) |
| `oos_folds` | no | complete walk-forward folds (+ optional pass ratio cap) |
| `parameter_plateau` | no | complete parameter neighbors (+ optional pass ratio cap) |
| `bootstrap_uncertainty` | no | bootstrap series length vs `block_length` (serial-dependence proxy) |
| `regime_coverage` | no | trade→regime coverage ratio |

**Aggregation:** `min_present` — worst present (non-`NOT_AVAILABLE`) label.
Any **required** dimension `NOT_AVAILABLE` → overall `NOT_AVAILABLE`.
`gate_integrity_status=INVALID` → overall `NOT_AVAILABLE`.

## Limitations (always visible)

- **serial_dependence:** `ASSESSED_VIA_BLOCK_BOOTSTRAP` when bootstrap inputs
  present; otherwise `LIMITATION` (dimension stays `NOT_AVAILABLE`).
- **multiple_testing:** `DOCUMENTED` when caller supplies metadata; otherwise
  `LIMITATION` with `variants_tested: null` — never invent variant counts.

## Artifact

Sealed write-once `confidence_profile.json` (+ `.sha256`) via
`write_confidence_profile_artifact` / `verify_confidence_profile_seal`.
Schema version `1.0`. Fields include `inputs` (raw evidence), `dimensions[]`,
`limitations[]`, `overall_label`, `policy_version`, `policy_content_hash`,
`decision_binding: false`, `auto_promotion: false`.

## Public API

```python
from research.confidence import (
    ConfidenceEvidenceInputs,
    evaluate_confidence,
    write_confidence_profile_artifact,
)

result = evaluate_confidence(inputs, policy_version="1.0")
write_confidence_profile_artifact(run_dir, result.to_artifact())
```

Scorecard HTTP surface and runner auto-write are deferred to #291 / follow-ups.
Advanced statistics (PSR/DSR/PBO/MTRL) are explicitly out of scope for #288.
