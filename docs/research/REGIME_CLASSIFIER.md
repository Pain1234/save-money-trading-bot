# Regime and Transition Classifier (P4.9)

**Status:** Implemented (generic Research Engine infrastructure)
**Issue:** [#285](https://github.com/Pain1234/save-money-trading-bot/issues/285)
**Contract:** [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) Layer 2 + §5; extends P5-03
([#199](https://github.com/Pain1234/save-money-trading-bot/issues/199)) without replacing it.
**Package:** `services/research/regime/`

## Purpose

Provide a **versioned, deterministic, content-hashed** calendar-month regime
classifier with an explicit transition/event layer. Output is a sealed
`regime_labels.json` artifact for later scorecard assembly
([#291](https://github.com/Pain1234/save-money-trading-bot/issues/291)).

This module does **not**:

- Open P5 holdout or freeze Strategy V1 parameters
- Encode private P5 partition-B volatility medians
- Create a second ExperimentRegistry or gate engine
- Auto-promote strategies

## Classifier version `1.0`

| Field | Value | Notes |
|-------|-------|-------|
| `period` | `calendar_month` | Period metrics use only bars inside the month |
| `trend_bull_min` | `0.05` | Same public +5% rule as #199 |
| `trend_bear_max` | `-0.05` | Same public −5% rule as #199 |
| `vol_low_max` | `0.015` | Generic public default (daily-return population stdev) |
| `vol_high_min` | `0.035` | Generic public default; not private P5 median |
| `min_bars_per_period` | `5` | Below → `INSUFFICIENT` (fail-closed) |
| `transition_window_bars` | `5` | Days tagged `TRANSITION_IN` / `TRANSITION_OUT` |
| `require_calendar_adjacency` | `true` | Missing months break transition chains |
| `labeling_mode` | `ex_post_period_attribution` | Day labels inherit completed-month labels |
| `point_in_time_safe` | `false` | Not for causal / live signals |

Identity binding: `classifier_version` **and**
`classifier_content_hash` (SHA-256 over canonical classifier JSON). Silent
edits under the same version fail closed
(`verify_classifier_content_hash`), matching the #248 gate-policy pattern.

### Taxonomy

- **Trend:** `BULL` \| `BEAR` \| `SIDEWAYS` \| `INSUFFICIENT`
- **Vol:** `LOW_VOL` \| `NORMAL_VOL` \| `HIGH_VOL` \| `INSUFFICIENT`
- **Event:** `TRANSITION_IN` \| `TRANSITION_OUT` \| `STABLE_REGIME` \| `INSUFFICIENT`

### Relationship to #199 High/Low vol

| #199 (P5 Strategy V1 contract) | P4.9 `1.0` |
|--------------------------------|------------|
| Bull / Bear / Sideways (+5% / −5%) | Same trend thresholds |
| High / Low vs private partition-B median | Three-way absolute bounds (public generic) |

Do **not** maintain a conflicting second taxonomy. Strategy V1 evaluation
continues to follow [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199);
freeze binding of private vol cutoffs to a classifier version is
[#294](https://github.com/Pain1234/save-money-trading-bot/issues/294).

## Determinism and dataset binding

`classification_id = clf_{sha256(canonical({classifier_version,
classifier_content_hash, dataset_id, dataset_content_hash, reference_symbol,
bars_content_hash}))}`

Same pins + same closes → same labels, transitions, distribution, and id.

## Ex-post attribution vs point-in-time

| Layer | Look-ahead rule |
|-------|-----------------|
| **Period** trend/vol | Uses only closes inside that calendar month (no cross-month look-ahead) |
| **Day** trend/vol / events | **Ex-post:** each day inherits the completed month label (#199). Completing the month can change earlier days' inherited labels. |
| **Transitions** | Only between **calendar-adjacent** months; gaps are recorded in `calendar_gaps` and do **not** fabricate skip transitions |

Artifact flags (binding for consumers / #291 API):

- `labeling_mode`: `ex_post_period_attribution`
- `point_in_time_safe`: `false`
- `usage.forbidden`: includes `point_in_time_signal`, `live_entry_filter`, `causal_intrabar_decision`
- Day / event rows include `"attribution": "period_ex_post"`

Do **not** feed day labels into a causal backtest decision path. Scorecard
Layer 2 / regime quality breakdowns are the intended consumers.

## Artifact

Path convention (sibling store, like robustness/gates):

```text
artifacts/research/regimes/<classification_id>/regime_labels.json
artifacts/research/regimes/<classification_id>/regime_labels.json.sha256
```

Overwrite of an existing sealed artifact is refused. Tampering fails
`verify_regime_labels_seal`.

Artifact fields include `period_labels`, `day_labels`, `transitions`,
`calendar_gaps`, `day_events`, and `distribution`. Missing/short periods use
`INSUFFICIENT` — never coerced to a zero score. Day/event rows are
ex-post attribution only (`point_in_time_safe=false`).

## Public / private

Safe in the public repository: classifier code, generic `1.0` thresholds,
synthetic fixtures, sealed empty-schema examples.

Must stay private / out of this repo: Strategy V1 OOS regime breakdown
tables, partition-B median values, accept/reject economic results.

## Reproducibility check

```text
python -m pytest tests/research/test_regime_classifier.py -q
```

## Non-scope (other issues)

- Regime quality metrics / worst-regime profile → [#287](https://github.com/Pain1234/save-money-trading-bot/issues/287)
- Behaviour labels / transition risk scoring → [#289](https://github.com/Pain1234/save-money-trading-bot/issues/289)
- Parameter-area stability → [#290](https://github.com/Pain1234/save-money-trading-bot/issues/290)
- Scorecard API / UI → [#291](https://github.com/Pain1234/save-money-trading-bot/issues/291) / [#292](https://github.com/Pain1234/save-money-trading-bot/issues/292)
