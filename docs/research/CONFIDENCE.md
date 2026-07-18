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
| `time_coverage` | no* | `equity_periods` (`len(equity)-1`) — time-length **proxy** only |
| `oos_folds` | no | complete walk-forward folds (+ optional pass ratio cap) |
| `parameter_plateau` | no | complete parameter neighbors (+ optional pass ratio cap) |
| `bootstrap_uncertainty` | no* | `floor(series_length / block_length)` effective block count |
| `regime_coverage` | no | trade→regime coverage ratio |

\*Required for overall **`HIGH`**: `trade_sample`, `time_coverage`, and
`bootstrap_uncertainty` must not be `NOT_AVAILABLE`. Additionally,
`multiple_testing` limitation must be `DOCUMENTED`. Otherwise a would-be
`HIGH` is capped to `MEDIUM` (missing core evidence must not omit into HIGH).

**Bootstrap:** `bootstrap_assessed=True` without both `bootstrap_series_length`
and `bootstrap_block_length >= 1` → dimension `NOT_AVAILABLE`. Measured value is
the effective block count, not raw series length.

**Aggregation:** `min_present_with_high_cap` — worst present (non-`NOT_AVAILABLE`)
label, then apply HIGH coverage cap. Any **required** dimension `NOT_AVAILABLE`
→ overall `NOT_AVAILABLE`. `gate_integrity_status=INVALID` → overall
`NOT_AVAILABLE`.

**Identity:** `confidence_id` binds run/dataset/policy pins **and**
`evidence_content_hash` over the canonical evaluated inputs (different raw
evidence → different id).

## Deferred to follow-up (#345)

Explicitly out of #288 implementation (still scorecard Layer-3 roadmap):

- Symbol / asset coverage dimension
- Concentration warnings (trade/period/symbol)
- Effective sample size with overlap / serial-dependence correction beyond
  block-count proxy
- True independent time-segment counting (beyond equity length proxy)
- PSR / DSR / PBO / MTRL

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
