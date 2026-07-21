# P5 Scorecard / Policy Bind (Freeze)

**Contract status:** `SCORECARD POLICY BIND FROZEN`. Current phase authority:
[P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md).
**Issue:** [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)
**ADR:** [ADR-020](../../DECISION_LOG.md#adr-020--strategy-v1-validation-binds-frozen-p49-scorecard-policy-versions)
**Extends:** [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198) / [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199) — does **not** replace them
**Holdout opened?** `NO`

## Purpose

After P4.9 generic infrastructure, Strategy V1 honest validation binds to
**pre-registered, content-hashed** scorecard / classifier / confidence /
behaviour (and related) policy versions **and** a fixed evaluation code
commit. This document records that bind.

It does **not**:

- open forward holdout C
- change ACCEPT/REJECT thresholds after seeing OOS
- emit automatic `ACCEPT_FOR_P6`
- publish private P5 economic results
- wait on Research Workspace UI [#292](https://github.com/Pain1234/save-money-trading-bot/issues/292)
  (see [Epic dependency amendment](#epic-dependency-amendment-292))

## Freeze identity

| Field | Value |
|-------|-------|
| Bind `origin/main` SHA | `5cb3a7bf2b310b15f932ccf24e934025990ebf6d` |
| Bind tip (short) | `5cb3a7bf2b31` (merge of #352 scorecard detail API) |
| Required `evaluation_code_commit` | **exactly** `5cb3a7bf2b310b15f932ccf24e934025990ebf6d` |
| Document author | Cursor agent (#294) |
| Document date (UTC) | 2026-07-19 |
| Human Freeze status | **SCORECARD POLICY BIND FROZEN** (`2026-07-19T12:53:03Z`) |

Recompute policy hashes against this SHA only. Silent edits under the same
version string must fail closed via content-hash mismatch. A new policy
version **or** any change to evaluation/labeling/transition code that should
affect Strategy V1 packs requires a **new GitHub issue + PR** and a **new
freeze SHA** (do not quietly advance `evaluation_code_commit`).

## Binding code commits (execution gate)

Policy content hashes seal **policy data**, not evaluator / labeling /
transition **code**. Strategy V1 scorecard and related research packs must
therefore also pin commits:

| Pin | Rule |
|-----|------|
| `evaluation_code_commit` | **Must equal** freeze SHA `5cb3a7bf2b310b15f932ccf24e934025990ebf6d`. Fail closed if different. |
| `run_code_commit` | **Must equal** the Candidate Freeze git pin from [#196](https://github.com/Pain1234/save-money-trading-bot/issues/196) / [P5_CANDIDATE_FREEZE.md](P5_CANDIDATE_FREEZE.md) once human comments `FREEZE APPROVED` + SHA. Until #196 is signed, packs are not execution-ready. |
| Drift | If `main` moves past the freeze SHA for evaluation code, **do not** run Strategy V1 validation under this bind — open a new #294-class rebind (or superseding ADR) with a new freeze SHA. |

Scorecards already persist `evaluation_code_commit` / `run_code_commit` on
records; Strategy V1 acceptance evidence must verify both against this table
and #196 before treating results as freeze-bound.

## Pinned layers (Strategy V1 validation bind)

Hashes verified on the freeze SHA via the registered `compute_*_content_hash`
helpers (`PYTHONPATH=services`).

| Layer | Module | Version | Content hash (SHA-256) | Pin source |
|-------|--------|---------|--------------------------|------------|
| Scorecard policy | `research.scorecard_policy` | `1.0` | `feb34430dae49a67833e580b99f05c79ba55e46d8af9f32135c35d7b68ab9e4b` | Literal `SCORECARD_POLICY_1_0_CONTENT_HASH` |
| Confidence policy | `research.confidence.policy` | `1.0` | `22748e176aa64ed36e01ac1911ac73b2314cb9ad22612b2206f80faec190d706` | Literal `CONFIDENCE_POLICY_1_0_CONTENT_HASH` |
| Behaviour policy | `research.regime_behaviour.policy` | `1.0` | `4b32808fdb861c24e900d8ab0a53f56213b86afb814aa2b75bf8bb6f47be6d78` | Computed at freeze SHA |
| Regime classifier | `research.regime.classifier` | `1.0` | `8dc21cb1be9c468c094e3ade19ca3b380c59541e5a621cbfd401bf4b77a54318` | Computed at freeze SHA |
| Transitions | `research.regime.transitions` | bound to classifier `1.0` | (same classifier hash + `evaluation_code_commit`) | No separate tunable version — sealed by classifier hash **and** freeze SHA |
| Gate policy (scorecard bind) | `research.gate_policy` | `1.1` | `3f3b0559d49c6158c78a2fe7e065d483a73829e7ab828455cf6b959e9cea8168` | Computed at freeze SHA (Layer-1 categories) |
| Gate policy (legacy ref) | `research.gate_policy` | `1.0` | `a589305b86745cb7ae1e1dde4b8e94e8dc6b6a8fd38a711d44f28415d54070c5` | Literal `POLICY_1_0_CONTENT_HASH` |
| Quality score policy | `research.regime_quality.scoring` | `1.0` | `14fe78c7ad3c53d163691b053d8a51689421b0d99b3e3ce7946ad919f84d83b4` | Computed (summary-only; not Strategy V1 ACCEPT gates) |
| Parameter-area policy | `research.parameter_area.policy` | `1.0` | `a5935ae7d7a7878434822032263f65f144b5d4122494e5bc50cec49869c35de7` | Computed (diagnostic plateau; not ACCEPT alone) |

**Scorecard evaluation for Strategy V1 packs** must pin **all** of:

- `evaluation_code_commit` = freeze SHA above
- `run_code_commit` = #196 Candidate Freeze SHA (when signed)
- `policy_version=1.0` + scorecard content hash above
- classifier / behaviour / confidence as produced under the versions above
- optional bound gate under **gate policy `1.1`** when gates are included

These are **infrastructure pins**. Numeric ACCEPT/REJECT/INCONCLUSIVE floors for
Strategy V1 remain in [P5_DECISION_RULES.md](P5_DECISION_RULES.md) / #198 and
become binding only after human `DECISION RULES FROZEN` on that issue.

## Regime taxonomy (single SoT for scorecard evidence)

**Decision (binding for #294):** For all Strategy V1 **scorecard / Research Engine
regime evidence** (labels, quality, behaviour, confidence joins, transitions),
the sole source of truth is **regime classifier `1.0`** at the freeze SHA:

- Trend: calendar-month return ±5% (Bull / Bear / Sideways) — aligned with #199 trend
- Vol: **three-way** `LOW_VOL` / `NORMAL_VOL` / `HIGH_VOL` via **public absolute**
  thresholds in classifier `1.0` (`vol_low_max` / `vol_high_min`), **not** the
  private partition-B median
- Transitions: directed ids + day events from `research.regime.transitions` as
  sealed under classifier `1.0` + `evaluation_code_commit`

**#199 private binary High/Low vs partition-B median** remains an optional
**private diagnostic overlay** for human reporting only. It is **not** the
scorecard cell taxonomy and must **not** be substituted for classifier `1.0`
labels in scorecards, gates, or ACCEPT evidence. There is **no** approved
deterministic mapping that collapses three-way absolute bands into the private
binary median for scorecard use under this freeze.

If Strategy V1 later needs the private median as the scorecard vol axis, that
requires a **new classifier version** + new freeze issue (not an in-place edit
of `1.0`).

See also [P5_BENCHMARKS_REGIMES.md](P5_BENCHMARKS_REGIMES.md) and
[`REGIME_CLASSIFIER.md`](../REGIME_CLASSIFIER.md).

Forbidden: post-hoc regime cherry-picking; dropping failed regimes after results;
mixing private-median labels into scorecard rows without a new versioned bind.

## Epic dependency amendment (#292)

Epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295) /
ADR-019 originally listed `#291 → #292 → #293 → #294`.

**Amendment for this bind:** [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)
may complete **without** waiting for UI [#292](https://github.com/Pain1234/save-money-trading-bot/issues/292).
Rationale: #294 is docs/governance pinning of already-merged evidence layers
(API/acceptance: #285–#291, #293, #350). #292 is Research Workspace UI binding
and remains open in parallel; it does not change sealed policy hashes or
`evaluation_code_commit`.

```text
P4.9 evidence layers (#284–#291, #293, #350) on main
  → #294 policy/code freeze (this document; Holdout closed)
  → {#251–#254} only after Human Freezes (#196–#199 + #294 sign-off)
#292 UI remains parallel / non-blocking for #294
```

Human sign-off on #294 acknowledges this amendment. Do **not** interpret checklist
“P4.9 infrastructure” as “#292 closed”.

## Holdout / OOS posture (binding for #294)

| Gate | State |
|------|-------|
| Holdout C opened? | **`NO`** |
| Holdout as optimization target? | **Forbidden** |
| #204 one-shot final OOS | **BLOCKED** until freezes + pre-OOS approval |
| #205 final decision | **BLOCKED** by #204 |
| Auto `ACCEPT_FOR_P6` from scorecard | **Never** |

Opening holdout C requires separate human process (Candidate Freeze #196,
partitions #197, protocol/decision #198, benchmarks #199, this bind signed,
private robustness packs, sample sufficiency, pre-OOS ADR note). See
[P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md).

## Human Freeze checklist

- [x] P4.9 **evidence** infrastructure on `main` (classifier, quality, confidence,
      behaviour, parameter area, scorecard API/detail, acceptance matrix; **not**
      requiring #292 UI)
- [x] Version + content-hash table recorded against freeze SHA
- [x] `evaluation_code_commit` pin = freeze SHA documented
- [x] `run_code_commit` rule tied to #196 Candidate Freeze documented
- [x] Single SoT taxonomy: classifier `1.0` for scorecard; #199 median = private overlay only
- [x] Epic chain amended: #294 not blocked by #292
- [x] #198 / #199 cross-linked without replacing proposed numeric gates
- [x] Holdout documented as closed
- [x] Human approver signed (`SCORECARD POLICY BIND FROZEN`)
- [x] Human `#196` / `#198` / `#199` freezes recorded separately

## Sign-off

| Role | Name | Date (UTC) | Comment |
|------|------|------------|---------|
| Author | Cursor agent (#294) | 2026-07-19 | Docs bind + P1 review fixes |
| Human approver | @Pain1234 | 2026-07-19T12:53:03Z | `SCORECARD POLICY BIND FROZEN` on #294 |

The bind is frozen. Current execution and #204 blockers are tracked only in
[P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md).

## Verification (docs / governance)

```text
PYTHONPATH=services python -c "from research.scorecard_policy import ..."
# Compare printed hashes to the table above at freeze SHA.
# Confirm evaluation_code_commit == 5cb3a7bf2b310b15f932ccf24e934025990ebf6d
```

No private Strategy V1 PnL, holdout calendars, or economic results in this file.
