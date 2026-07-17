# P5 Validation Protocol

**Status:** THRESHOLDS PROPOSED — awaiting human freeze
**Issue:** [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198) (P5-02)
**Hard rule:** Freeze and human-approve this protocol **before** opening the final OOS dataset. Never change thresholds after seeing results.

## 1. Research question

Under pre-registered costs, benchmarks, partitions, and decision rules, does frozen Strategy V1 (`trend_v1` @ `1.0.0`) produce evidence sufficient for `ACCEPT_FOR_P6`, or must it be `REJECT` / `INCONCLUSIVE`?

## 2. Candidate identity

Reference signed [P5_CANDIDATE_FREEZE.md](P5_CANDIDATE_FREEZE.md).

## 3. Data partitions

Reference [P5_DATA_EXPOSURE_AUDIT.md](P5_DATA_EXPOSURE_AUDIT.md):

- A Development / Seen
- B Walk-Forward / Validation (only cleared `VALIDATION_ELIGIBLE`)
- C Forward holdout (sealed until #204)

**Purge/embargo:** 90 calendar days (proposed; human approve with #197).

## 4. Benchmarks

See [P5_BENCHMARKS_REGIMES.md](P5_BENCHMARKS_REGIMES.md) (#199). Minimum:

| Benchmark | ID / version |
|-----------|----------------|
| Cash / null | `cash_null@1.0` |
| Buy-and-hold per symbol | P4 `buy_and_hold_<SYMBOL>@1.0` |
| Equal-weight BTC/ETH/SOL | `eq_weight_btc_eth_sol@1.0` (monthly rebalance) |

## 5. Cost assumptions

- Base: P4 fee/slippage/funding (`COST_MODEL_VERSION` `1.1`).
- Stress scenarios (#201): base, fee×2, slippage×2, funding on+stress, combined elevated, combined extreme.
- Gross and net always separated.
- No post-hoc stress shopping.

## 6. Metrics (decision-relevant)

As listed in planning: performance, risk, trade-level, stability. No single metric alone promotes.

## 7. Robustness tests

| Test | Issue | Constraint |
|------|-------|------------|
| Walk-forward (fixed params) | #200 | No per-fold optimization |
| Cost / funding stress | #201 | Pre-registered scenarios |
| Parameter neighborhood | #202 | Diagnostic only |
| Bootstrap / Monte Carlo | #203 | Time-respecting methods |

## 8. Sample sufficiency (proposed — human must approve)

| Rule | Proposed value | Rationale | Stricter | Looser | Human approval |
|------|----------------|-----------|----------|--------|----------------|
| Min closed trades (total, OOS) | 30 | Practical floor; still statistically weak for heavy tails | More INCONCLUSIVE | False ACCEPT risk | Pending |
| Min closed trades / symbol | 5 | Detect single-symbol lottery | May exclude thin symbols | Mask concentration | Pending |
| Min walk-forward folds | 3 | Minimum chronological diversity | Harder pass | Regime blind spots | Pending |
| Min distinct regimes (OOS) | 2 | Avoid single-phase luck | Harder pass | Phase luck | Pending |
| Min OOS duration | 90 calendar days | Aligns with embargo / one quarter | Wait longer | Weak OOS | Pending |
| Max PnL share from top-3 trades | 50% | Fragility guard | Reject fragile edges | Allow lottery | Pending |
| Symbols below floor | Exclude from ACCEPT; document | — | — | — | Pending |

If sufficiency fails → `INCONCLUSIVE` (not `ACCEPT_FOR_P6`).

## 9. Accept / Reject / Inconclusive

See [P5_DECISION_RULES.md](P5_DECISION_RULES.md).

## 10. Evaluation order (binding)

1. Entry gate + freezes + #181
2. Optional development reproduction (not decision)
3. Walk-forward on B
4. Cost stress
5. Parameter stability
6. Bootstrap/MC
7. Sample sufficiency
8. Human pre-OOS approval
9. One-shot final OOS (C)
10. Decision rules + human sign-off (#205)

## 11–16. Errors / data / missing trades / hypotheses / perturbations / OOS

As in original protocol: fail-closed, quarantine, sufficiency→INCONCLUSIVE, one frozen candidate, diagnostics-only perturbations, private OOS storage, no retuning.

## 17. Public / private

[P5_PUBLIC_PRIVATE_ARTIFACTS.md](P5_PUBLIC_PRIVATE_ARTIFACTS.md).

## 18. Human gates

| Gate | Required before |
|------|-----------------|
| Protocol + decision freeze | Holdout open |
| Pre-OOS approval | #204 |
| Final decision | Close #47 / milestone |

## Seeds / versions

| Item | Value |
|------|-------|
| Primary random seed | `42` |
| Metrics schema | `1.1` |
| Cost model | `1.1` |

## Protocol freeze sign-off

| Role | Name | Date |
|------|------|------|
| Author | Cursor agent (P5 execution) | 2026-07-17 |
| Human approver | **REQUIRED** — comment on #198: `PROTOCOL FROZEN` | |

**Thresholds mutable after freeze?** `NO`
