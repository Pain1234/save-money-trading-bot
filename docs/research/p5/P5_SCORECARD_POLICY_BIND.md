# P5 Scorecard / Policy Bind (Freeze)

**Status:** `PENDING_HUMAN_SIGN_OFF`  
**Issue:** [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)  
**ADR:** [ADR-020](../../DECISION_LOG.md#adr-020--strategy-v1-validation-binds-frozen-p49-scorecard-policy-versions)  
**Extends:** [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198) / [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199) — does **not** replace them  
**Holdout opened?** `NO`

## Purpose

After P4.9 generic infrastructure, Strategy V1 honest validation binds to
**pre-registered, content-hashed** scorecard / classifier / confidence /
behaviour (and related) policy versions. This document records that bind.

It does **not**:

- open forward holdout C
- change ACCEPT/REJECT thresholds after seeing OOS
- emit automatic `ACCEPT_FOR_P6`
- publish private P5 economic results

## Freeze identity

| Field | Value |
|-------|-------|
| Bind `origin/main` SHA | `5cb3a7bf2b310b15f932ccf24e934025990ebf6d` |
| Bind tip (short) | `5cb3a7bf2b31` (merge of #352 scorecard detail API) |
| Document author | Cursor agent (#294) |
| Document date (UTC) | 2026-07-19 |
| Human Freeze status | **PENDING_HUMAN_SIGN_OFF** |

Recompute hashes against this SHA only. Silent edits under the same version
string must fail closed via content-hash mismatch. A new policy version requires
a **new GitHub issue + PR**, not an in-place edit.

## Pinned layers (Strategy V1 validation bind)

Hashes verified on the freeze SHA via the registered `compute_*_content_hash`
helpers (`PYTHONPATH=services`).

| Layer | Module | Version | Content hash (SHA-256) | Pin source |
|-------|--------|---------|--------------------------|------------|
| Scorecard policy | `research.scorecard_policy` | `1.0` | `feb34430dae49a67833e580b99f05c79ba55e46d8af9f32135c35d7b68ab9e4b` | Literal `SCORECARD_POLICY_1_0_CONTENT_HASH` |
| Confidence policy | `research.confidence.policy` | `1.0` | `22748e176aa64ed36e01ac1911ac73b2314cb9ad22612b2206f80faec190d706` | Literal `CONFIDENCE_POLICY_1_0_CONTENT_HASH` |
| Behaviour policy | `research.regime_behaviour.policy` | `1.0` | `4b32808fdb861c24e900d8ab0a53f56213b86afb814aa2b75bf8bb6f47be6d78` | Computed at freeze SHA |
| Regime classifier | `research.regime.classifier` | `1.0` | `8dc21cb1be9c468c094e3ade19ca3b380c59541e5a621cbfd401bf4b77a54318` | Computed at freeze SHA |
| Transitions | `research.regime.transitions` | bound to classifier `1.0` | (same classifier hash) | No separate tunable version — part of classifier contract |
| Gate policy (scorecard bind) | `research.gate_policy` | `1.1` | `3f3b0559d49c6158c78a2fe7e065d483a73829e7ab828455cf6b959e9cea8168` | Computed at freeze SHA (Layer-1 categories) |
| Gate policy (legacy ref) | `research.gate_policy` | `1.0` | `a589305b86745cb7ae1e1dde4b8e94e8dc6b6a8fd38a711d44f28415d54070c5` | Literal `POLICY_1_0_CONTENT_HASH` |
| Quality score policy | `research.regime_quality.scoring` | `1.0` | `14fe78c7ad3c53d163691b053d8a51689421b0d99b3e3ce7946ad919f84d83b4` | Computed (summary-only; not Strategy V1 ACCEPT gates) |
| Parameter-area policy | `research.parameter_area.policy` | `1.0` | `a5935ae7d7a7878434822032263f65f144b5d4122494e5bc50cec49869c35de7` | Computed (diagnostic plateau; not ACCEPT alone) |

**Scorecard evaluation for Strategy V1 packs** must pin:

- `policy_version=1.0` + scorecard content hash above
- classifier / behaviour / confidence as produced under the versions above
- optional bound gate under **gate policy `1.1`** when gates are included

These are **infrastructure pins**. Numeric ACCEPT/REJECT/INCONCLUSIVE floors for
Strategy V1 remain in [P5_DECISION_RULES.md](P5_DECISION_RULES.md) / #198 and
become binding only after human `DECISION RULES FROZEN` on that issue.

## Consistency with #199 (benchmarks / regimes)

[P5_BENCHMARKS_REGIMES.md](P5_BENCHMARKS_REGIMES.md) defines the Strategy V1
**evaluation contract** for monthly trend/vol reporting. P4.9 classifier `1.0`
is the **versioned Research Engine** implementation of that taxonomy (including
explicit transitions). Do **not** maintain a conflicting second taxonomy.

- Freeze before final holdout (this document + #199 human approval).
- Forbidden: post-hoc regime cherry-picking; dropping failed regimes after results.

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

- [x] P4.9 infrastructure on `main` (classifier, quality, confidence, behaviour,
      parameter area, scorecard API/detail, acceptance matrix)
- [x] Version + content-hash table recorded against freeze SHA
- [x] #198 / #199 cross-linked without replacing proposed numeric gates
- [x] Holdout documented as closed
- [ ] Human approver signs below (`SCORECARD POLICY BIND FROZEN`)
- [ ] Human `#198` / `#199` freezes (separate issues; still required before #204)

## Sign-off

| Role | Name | Date (UTC) | Comment |
|------|------|------------|---------|
| Author | Cursor agent (#294) | 2026-07-19 | Docs bind prepared |
| Human approver | **REQUIRED** | | Comment `SCORECARD POLICY BIND FROZEN` on #294 / this PR |

Until human sign-off, treat status as **pending**. Docs may merge for review;
execution of #251–#254 / #204 must wait for freezes including this bind.

## Verification (docs / governance)

```text
PYTHONPATH=services python -c "from research.scorecard_policy import ..."
# Compare printed hashes to the table above at freeze SHA.
```

No private Strategy V1 PnL, holdout calendars, or economic results in this file.
