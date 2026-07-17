# P5 – Honest Validation of Trend Strategy V1 (planning)

**Status:** PLANNING ONLY
**Milestone:** [P5 – Honest Validation of Trend Strategy V1](https://github.com/Pain1234/save-money-trading-bot/milestone/6)
**Canonical risk issue:** [#47](https://github.com/Pain1234/save-money-trading-bot/issues/47) (R-003)
**Canonical public/private issue:** [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181)

## Purpose (binding)

P5 does **not** prove that Strategy V1 is profitable.

P5 decides honestly whether the already-defined, frozen Strategy V1 under pre-registered rules:

1. provides credible evidence for promotion to P6 (`ACCEPT_FOR_P6`),
2. must be rejected (`REJECT`), or
3. lacks sufficient evidence (`INCONCLUSIVE`).

`INCONCLUSIVE` is **not** a promotion.

Goal: filter bad, overfit, or under-evidenced strategies — not make a strategy look good by testing.

## Roadmap position

```text
P4 – Research Engine (complete on main)
  → P5 – Honest Validation of Trend Strategy V1  ← this milestone
    → P6 – Paper Trading Soak
      → P7 / P8 / P9 (not pre-empted by P5)
```

P5 must not pre-empt paper soak, multi-asset work, or live trading.

## Binding dependency chain

```text
P4 complete on main
  → #181 Public/Private Separation
    → P5-00 #196 Entry Gate + Candidate Freeze
      → P5-01 #197 Data Exposure Audit + Partition Lock
        → P5-02 #198 Protocol + Decision Freeze
          → P5-03 #199 Benchmarks + Regimes
            → {P5-04 #200 Walk-Forward, P5-05 #201 Cost Stress,
               P5-06 #202 Parameter Stability, P5-07 #203 Bootstrap/MC}
              → Human Pre-OOS Approval
                → P5-08 #204 Final Untouched OOS Once
                  → P5-09 #205 Final Decision
                    → ACCEPT_FOR_P6 → P6
                    → REJECT → no promotion
                    → INCONCLUSIVE → gather evidence, no promotion
```

Canonical: [#47](https://github.com/Pain1234/save-money-trading-bot/issues/47), [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181).

## Planning documents (this folder)

| Document | Role |
|----------|------|
| [P5_DATA_EXPOSURE_AUDIT.md](P5_DATA_EXPOSURE_AUDIT.md) | Classify historical periods; lock partitions |
| [P5_CANDIDATE_FREEZE.md](P5_CANDIDATE_FREEZE.md) | Freeze Strategy V1 candidate identity |
| [P5_VALIDATION_PROTOCOL.md](P5_VALIDATION_PROTOCOL.md) | Pre-register all checks before final OOS |
| [P5_DECISION_RULES.md](P5_DECISION_RULES.md) | ACCEPT / REJECT / INCONCLUSIVE gates |
| [P5_BENCHMARKS_REGIMES.md](P5_BENCHMARKS_REGIMES.md) | Benchmarks + deterministic regimes (#199) |
| [P5_EXECUTION_STATUS.md](P5_EXECUTION_STATUS.md) | Live execution gate status (no metrics) |
| [P5_ROBUSTNESS_PLANS.md](P5_ROBUSTNESS_PLANS.md) | WF / cost / stability / bootstrap plans (#200–#203) |
| [P5_PUBLIC_PRIVATE_ARTIFACTS.md](P5_PUBLIC_PRIVATE_ARTIFACTS.md) | Artifact classification (#181) |
| [P5_EXECUTION_CHECKLIST.md](P5_EXECUTION_CHECKLIST.md) | Operational gates and stop rules |
| [P5_PHASE_A_AUDIT.md](P5_PHASE_A_AUDIT.md) | Phase A inventory (evidence-based) |

Templates and placeholders only until human-approved execution. **No real OOS results in this folder or in public GitHub.**

## Entry gate (summary)

P5 remains PLANNING ONLY until every item in [P5_EXECUTION_CHECKLIST.md](P5_EXECUTION_CHECKLIST.md) § Entry gate is evidenced. Missing prerequisites become blocking issues; no experiment start; no holdout open.

## Outcomes

| Outcome | Meaning | Next |
|---------|---------|------|
| `ACCEPT_FOR_P6` | Pre-registered gates passed; human sign-off | Open P6 gate |
| `REJECT` | Failed pre-registered reject rules | No promotion; new version required for retry |
| `INCONCLUSIVE` | Insufficient sample / holdout / evidence | No promotion; define next evidence |

## Explicit non-scope (this planning work)

- No backtests executed as part of planning
- No final OOS window opened
- No strategy parameter changes
- No new strategy, assets, HYPE, HIP-3, paper soak, live trading, or deployment
- No automatic merge

## Related public-core docs

- `docs/strategy-specification.md`, `docs/strategy-v1-parameter-inventory.md`
- `docs/risk-specification.md`
- `docs/research/*` (P4 contracts)
- `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md`
- `docs/STRATEGY_LIFECYCLE.md`, `ROADMAP.md`
