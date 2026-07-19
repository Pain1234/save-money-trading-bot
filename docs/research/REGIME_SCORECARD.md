# Regime-Based Strategy Evidence Scorecard (P4.9)

- **Status:** CONTRACT (governance) — runtime implementation tracked under Epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295)
- **Contract issue:** [#284](https://github.com/Pain1234/save-money-trading-bot/issues/284)
- **ADR:** ADR-019 in `docs/DECISION_LOG.md`
- **Related delivered infrastructure:** ExperimentRegistry (#141–#147), Robustness (#247), Gates (#248), Validation Studies (#249)
- **P5 freeze anchors:** [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198), [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199)
- **Public/private:** [`docs/governance/PUBLIC_PRIVATE_BOUNDARY.md`](../governance/PUBLIC_PRIVATE_BOUNDARY.md), [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181)

This document is the **versioned contract** for a regime-based evidence scorecard.
It does **not** implement the scorecard runtime, does **not** freeze private
Strategy V1 numeric thresholds, does **not** open the final holdout, and does
**not** authorize paper/live promotion.

---

## 1. Purpose

Answer these questions **separately** (never collapse into one compensating score):

1. Is the research run methodologically valid?
2. Does the strategy pass critical robustness and risk gates?
3. How does it perform in each market regime?
4. How strong is that statement (evidence confidence)?
5. Does behaviour match the strategy hypothesis in each regime?
6. What is the worst regime / largest weakness (incl. transitions)?
7. Is there a stable parameter **area**, or only an isolated peak?
8. Does the finding survive realistic costs and independent OOS segments?

Primary consumers: human reviewers, Validation Studies (#249), P5 decision process
(#205). The scorecard is an **evidence profile**, not an auto-decision engine.

---

## 2. Architecture boundary (binding)

### Allowed pipeline

```text
Research experiment
→ immutable run artifacts
→ robustness evidence
→ integrity evaluation
→ critical gate evaluation
→ regime evidence profile
→ validation study
→ human decision
```

### Forbidden

```text
Research experiment
→ second scorecard database
→ second gate service
→ separate results registry
→ automatic promotion
```

### Reuse (do not duplicate)

| Component | Role |
|-----------|------|
| `ExperimentRegistry` | Run source of truth |
| Robustness manifests (#247) | Walk-forward, cost stress, parameter stability, bootstrap |
| `GatePolicy` / `GateEvaluator` / `GateResultStore` (#248) | Versioned gates, append-only results |
| `ValidationStudy` (#249) | Pinned evidence snapshots + human decision |
| Research API + Workspace UI | Read surfaces; Public/Private boundary |

Generic P4 policy **must not** hard-code private P5 Strategy V1 numbers.
Strategy-specific thresholds remain human-controlled under P5 ([#198](https://github.com/Pain1234/save-money-trading-bot/issues/198), [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)).

---

## 3. Layer model (fixed)

### Layer 0 — Research Integrity (binary)

| Status | Meaning |
|--------|---------|
| `VALID` | Integrity checks passed; quality/gates may proceed |
| `INVALID` | Fail-closed; no trusted quality scores or promotions |
| `NOT_VERIFIABLE` | Required evidence missing or cannot be checked |

**Non-compensable.** Failed integrity must not be scored away.

Minimum checks (extend via versioned policy; fail closed on doubt):

- Dataset ID and content hash match sealed run binding
- Run artifacts and checksums verify (registry trust anchor)
- Git commit and configuration are reconstructible
- No open/future candles; no data leakage; no look-ahead
- Correct signal vs execution timestamps
- Reproducible results; consistent accounting
- Realistic fee / funding / slippage identity vs Spec
- No corrupted or invalidated evidence artifacts
- Sufficient trade→regime assignment coverage for claimed regime metrics

On integrity failure:

- Scorecard status = `INVALID`
- Do **not** compute quality scores for decision use
- Do **not** present gate evaluation as trusted promotion evidence
- Do **not** emit positive summary / promotion affordances

**Implementation ([#286](https://github.com/Pain1234/save-money-trading-bot/issues/286)):**
persisted on `GateRunRecord` as `integrity_status` + `integrity_checks`.
Trusted quality scoring gate:
`research.gate_evaluator.quality_scores_permitted(record)` → true only for
active + `VALID`. Mandatory checks that are not yet automated (look-ahead,
fee-vs-spec, regime coverage) are recorded as `not_verifiable`, so evaluate
results stay `NOT_VERIFIABLE` until those verifiers exist — never silent
`VALID`. See [GATES.md](GATES.md).

### Layer 1 — Critical Gates

Versioned, evidence-bound gates (extend [#248](https://github.com/Pain1234/save-money-trading-bot/issues/248) / [GATES.md](GATES.md)).

| Result | Meaning |
|--------|---------|
| `PASS` | Measured evidence meets gate under bound policy |
| `FAIL` | Measured evidence fails gate |
| `INCONCLUSIVE` | Evidence present but insufficient to decide |
| `NOT_AVAILABLE` | Required inputs missing (never treat as PASS) |

Minimum gate **categories** (thresholds versioned; generic policy has no private V1 numbers):

- Max drawdown bound → policy `1.1` category `drawdown`
- OOS net result after costs → `oos_net`
- Walk-forward stability → `walk_forward`
- Cost stress → `cost_stress`
- Parameter fragility → `parameter_fragility`
- Trade / period / symbol concentration → reserved (`concentration`)
- Bootstrap / Monte Carlo tail result → `bootstrap`
- Adequate regime coverage → reserved (`regime_coverage`)
- Minimum evidence / sample sufficiency → `sample_sufficiency`
- Execution realism → reserved (`execution_realism`)

**Rule:** A strong regime quality profile must not compensate a failed critical gate.
Policy `1.1` labels the shipped generic gates; missing evidence → `NOT_AVAILABLE`.

### Layer 2 — Regime Quality

Evaluate **per regime**, not only portfolio aggregate.

#### Starting taxonomy (freeze before final holdout)

- **Trend axis:** `BULL` | `BEAR` | `SIDEWAYS`
- **Volatility axis:** `LOW_VOL` | `NORMAL_VOL` | `HIGH_VOL`
- **Event layer:** `TRANSITION_IN` | `TRANSITION_OUT` | `STABLE_REGIME`

Runtime classifier (Issue [#285](https://github.com/Pain1234/save-money-trading-bot/issues/285)):
`services/research/regime/`, contract
[`REGIME_CLASSIFIER.md`](REGIME_CLASSIFIER.md), starting version `1.0`
(content-hashed; sealed `regime_labels.json`).

Per-regime raw quality metrics (Issue [#287](https://github.com/Pain1234/save-money-trading-bot/issues/287)):
`services/research/regime_quality/`, contract
[`REGIME_QUALITY.md`](REGIME_QUALITY.md), sealed `regime_metrics.json`
(worst/strongest from raw net PnL; summary score never sole decision).

Final taxonomy, thresholds, windows, and `classifier_version` must be frozen
before the final holdout ([#199](https://github.com/Pain1234/save-money-trading-bot/issues/199), [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)).
**Forbidden:** post-hoc regime selection to hide bad results.

Per-regime minimum metrics (raw values remain visible):

- Net / gross return or PnL; costs
- Maximum drawdown; downside risk; tail loss
- Benchmark delta (same period + dataset)
- Trade count; exposure; time in market; turnover
- Win rate / expectancy / profit factor **only if defined and sample-sensible**
- Largest losing streak; PnL concentration
- Subperiod stability; symbol contributions

Quality score (e.g. 0–10) is an optional **versioned summary** only:

- Weights are versioned and content-hashed
- Score never replaces raw metrics
- Decisions must not be made on score alone
- Missing data → `NOT_AVAILABLE`, **never** silently coerced to `0`

### Layer 3 — Evidence Confidence

Quality and confidence stay separate.

Confidence is derived from measurable inputs (not free manual estimate), e.g.:

- Effective sample size; closed trades; independent time segments; OOS folds
- Regime / asset coverage; subperiod stability
- Bootstrap intervals; serial dependence; trade/position overlap
- Number of variants tested; multiple-testing risk
- Parameter-plateau stability; track-record length

| Label | Meaning |
|-------|---------|
| `HIGH` | Strong measurable support |
| `MEDIUM` | Adequate but limited |
| `LOW` | Weak support |
| `INSUFFICIENT` | Below documented floors |
| `NOT_AVAILABLE` | Required inputs missing |

**Implementation ([#288](https://github.com/Pain1234/save-money-trading-bot/issues/288)):**
`services/research/confidence/` + contract [`CONFIDENCE.md`](CONFIDENCE.md).
Versioned policy `1.0` (content-hashed), sealed `confidence_profile.json`,
visible serial-dependence / multiple-testing limitations, HIGH coverage cap
when core dimensions or documented multiple-testing are missing, bootstrap
measured as effective block count. Deeper coverage (symbol, concentration,
effective-n, true independent segments, PSR/DSR/PBO/MTRL) →
[#345](https://github.com/Pain1234/save-money-trading-bot/issues/345).

Advanced statistics (PSR, DSR, PBO, MTRL) may be added only when:

- formula and version are documented,
- required inputs exist,
- synthetic reference tests exist,
- missing inputs → `NOT_AVAILABLE` (no fantasy formulas for UI).

### Layer 4 — Behaviour Profile

Per-regime labels from **documented deterministic rules** over raw metrics.
No LLM output as persisted research result. Optional human-readable summary
must be clearly separated from deterministic labels.

Runtime (Issue [#289](https://github.com/Pain1234/save-money-trading-bot/issues/289)):
`services/research/regime_behaviour/`, contract
[`REGIME_BEHAVIOUR.md`](REGIME_BEHAVIOUR.md), sealed `behavior_profile.json`.

Example labels:

`PROFITABLE` · `DEFENSIVE_INACTIVE` · `CONTROLLED_BLEED` · `WHIPSAW_PRONE` ·
`LATE_EXIT` · `LATE_ENTRY` · `OVERACTIVE_REENTRY` · `COST_INTENSIVE` ·
`TAIL_RISK_EXPOSED` · `SHOCK_DEPENDENT` · `INSUFFICIENT_EVIDENCE`

**Trend-following rule:** Sideways need not be profitable. Low activity, low
cost, low exposure, bounded losses, and no tail damage can be **good** behaviour.
Zero trades must not automatically be treated as failure.

### Layer 5 — Global Evidence Profile

At least:

- Integrity status; Critical gates status
- Worst regime; Worst transition; Strongest regime
- Cost-stress boundary; Parameter-area stability
- Evidence confidence summary; Benchmark delta
- Main weakness; Main strength; Concentration warnings
- Final human decision if present (from Validation Study / P5)

A weighted aggregate score, if any, is at most a **sort aid**. It must not:

- override critical gate FAIL,
- upgrade `INVALID` runs,
- auto-emit `ACCEPT` / `ACCEPT_FOR_P6`,
- activate paper or live trading.

---

## 4. Parameter area (plateau), not single optimum

Question shifted from “best single parameter set?” to:

> Is there a contiguous neighbourhood of parameters where the claim remains stable?

Report at least:

- Frozen parameter point (unchanged; no auto-retune)
- Neighbours tested; share positive; share passing gates
- Median / dispersion of neighbour results; steepest local drop
- Plateau size; contiguous stable region; isolated optimum yes/no

Classification: `BROAD_STABLE_PLATEAU` | `NARROW_STABLE_AREA` |
`ISOLATED_PEAK` | `UNSTABLE` | `INSUFFICIENT_EVIDENCE`

Implemented: `services/research/parameter_area/` + contract
[`PARAMETER_AREA.md`](PARAMETER_AREA.md), sealed `parameter_area.json`.

Reuse #247 parameter-stability artefacts. Do not build plateaus from final OOS /
holdout data. P5 Strategy V1 remains on the frozen point.

---

## 5. Transitions (explicit module)

Monthly regime labels alone can hide fast switches. Versioned transition
detection ships with classifier `1.0` ([#285](https://github.com/Pain1234/save-money-trading-bot/issues/285);
[`REGIME_CLASSIFIER.md`](REGIME_CLASSIFIER.md)). Transition **quality /
behaviour scores** remain later issues (#287 / #289). The module covers:

- Windows before / at / after regime change
- Change direction; volatility jump
- Time to de-risk / direction change; turnover during transition
- Extra slippage/cost load; maximum adverse excursion in transition

Example transition ids: `BULL_TO_BEAR`, `BEAR_TO_BULL`, `TREND_TO_SIDEWAYS`,
`SIDEWAYS_TO_TREND`, `LOW_TO_HIGH_VOL`, `HIGH_TO_LOW_VOL`.

Transition scores are **separate** from stable-regime quality.
Definitions must be deterministic, versioned, documented, and frozen before
final holdout.

---

## 6. Versioning, freeze, missing data, invalidation

| Object | Versioning rule |
|--------|-----------------|
| Scorecard schema | Explicit `schema_version`; additive changes preferred |
| Gate / scorecard policy | `policy_version` **and** content hash (#248 pattern) |
| Regime classifier | `classifier_version` + content hash + dataset binding |
| Behaviour / confidence rules | Version + content hash |
| Quality weights | Version + content hash |

**Freeze:** After human freeze for a P5 candidate evaluation path, changing
weights, regime bounds, transition windows, or gate thresholds for that
evaluation is forbidden until a new study / new policy version is explicitly
opened. Final holdout must not be an optimization target.

**Missing data:** Always `NOT_AVAILABLE` / `INCONCLUSIVE` as specified — never `0`.

**Invalidation:** Append-only (registry / gate / study / scorecard sidecars).
Never mutate sealed run manifests. See [INVALIDATION.md](INVALIDATION.md).

---

## 7. Anti-overfitting and no auto-promotion

Binding rules:

1. No monolithic decision score that overrides integrity or critical gates.
2. No post-hoc regime / fold / symbol cherry-picking.
3. No silent policy mutation under the same version string (content hash fails closed).
4. No automatic paper or live promotion from scorecard or gate `PASS`.
5. No private Strategy V1 economic results in the public repository.
6. No optimizing directly against a total score or against the final holdout.
7. Human decision remains external (`ValidationStudy` decision API; P5 `#205`).

---

## 8. Proposed artifacts and API (implementation issues)

**Status (#291):** Append-only scorecard store + Research API are implemented —
see [`SCORECARDS.md`](SCORECARDS.md). Layer inputs are sealed run-dir artifacts
and/or sibling stores (gates, robustness); aggregate scorecards live under
`artifacts/research/scorecards/` (not a second experiment registry).
`parameter_area` remains `NOT_AVAILABLE` until #290 lands.

Layer input artifacts (produced by earlier issues; names may refine):

- `regime_labels.json`
- `regime_metrics.json`
- `confidence_profile.json`
- `behavior_profile.json`
- `parameter_area.json` (pending #290)
- Aggregate: `scorecard_id` `sc_{sha256…}` in `registry.jsonl` (not run-dir `scorecard.json`)

API (extend existing Research API; no second registry):

- `GET /api/v1/research/scorecards/policies`
- `GET /api/v1/research/scorecards`
- `GET /api/v1/research/scorecards/{scorecard_id}`
- `POST /api/v1/research/scorecards/evaluate` — idempotent evidence evaluation only
- `POST /api/v1/research/scorecards/{scorecard_id}/invalidate` — append-only

`scorecard_id` is deterministic from pinned inputs + policy content hash.
ValidationStudy schema `1.2` pins `scorecard_ids` into the evidence snapshot.

---

## 9. Issue map (P4.9)

| Issue | Title |
|-------|-------|
| [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295) | Epic P4.9 |
| [#284](https://github.com/Pain1234/save-money-trading-bot/issues/284) | Contract (this document) |
| [#285](https://github.com/Pain1234/save-money-trading-bot/issues/285) | Regime / transition classifier |
| [#286](https://github.com/Pain1234/save-money-trading-bot/issues/286) | Integrity + critical gate categories |
| [#287](https://github.com/Pain1234/save-money-trading-bot/issues/287) | Regime quality metrics |
| [#288](https://github.com/Pain1234/save-money-trading-bot/issues/288) | Evidence confidence |
| [#289](https://github.com/Pain1234/save-money-trading-bot/issues/289) | Behaviour + transition risk |
| [#290](https://github.com/Pain1234/save-money-trading-bot/issues/290) | Parameter area stability |
| [#291](https://github.com/Pain1234/save-money-trading-bot/issues/291) | Artifacts + API |
| [#292](https://github.com/Pain1234/save-money-trading-bot/issues/292) | Research Workspace UI |
| [#293](https://github.com/Pain1234/save-money-trading-bot/issues/293) | E2E / anti-overfit acceptance — API matrix in `test_scorecard_e2e_acceptance.py`; UI deferred to #292/#250 |
| [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294) | P5 binding / freeze (P5 milestone) |

### Dependency chain

```text
P4 existing engine
→ #284 Contract
→ #285 Regime/Transition Classifier
→ #286 Integrity/Gates
→ {#287 Quality, #288 Confidence, #289 Behaviour, #290 Parameter Area}
→ #291 Artifact/API
→ #292 UI
→ #293 E2E
→ #294 P5 Binding/Freeze
→ P5 execution #251–#254
→ human pre-OOS gate
→ #204 one-shot final OOS
→ #205 human decision
```

---

## 10. Non-scope (this contract and Epic #295)

- New strategy; parameter optimization; final P5 holdout execution
- Automatic live-trading recommendation
- New assets; HIP-3 implementation; ML regime detection
- Dynamic regime bounds fitted after seeing evaluation results
- Optimization targeting a total score
- Second experiment or validation registry
- Paper/live promotion hooks
