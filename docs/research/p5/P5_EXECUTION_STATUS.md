# P5 Execution Status

**Updated:** 2026-07-17
**Holdout opened?** `NO`

## Wave completion (public core)

One GitHub issue per branch/PR (AGENTS.md / DoD). No silent multi-issue bundling.

| Wave | Issue | Public deliverable | Blocking human / time gate |
|------|-------|--------------------|----------------------------|
| 0 | #181 | Private repo + leakage docs | **Merged** (PR #222); confirm private ACL |
| 1 | #196 | Candidate freeze prepared (metrics **1.2**) | `FREEZE APPROVED` + **final merged main** SHA + refreshed 76+3 |
| 2 | #197 | Partitions / exposure audit | `PARTITIONS LOCKED` + embargo + monthly warmup ack |
| 3 | #198 | Protocol + decision rules | `PROTOCOL FROZEN` / `DECISION RULES FROZEN` |
| 4 | #199 | Benchmarks / regimes | Human approval (metrics 1.2 / Spec cost parity) |
| 5a | #200 | Walk-forward helper | Private B runs after freezes |
| 5b | #201 | Cost-stress scenarios | Private B runs after freezes |
| 5c | #202 | Parameter neighborhood | Private B runs after freezes |
| 5d | #203 | Path bootstrap helper | Private B runs after freezes |
| 6 | #204 | Pre-OOS gate checklist below | All freezes + sufficiency + pre-OOS approval |
| 7 | #205 | Decision process / ADR | After #204 once |

## Pre-OOS hard stop (#204)

Do **not** open holdout C until all are true:

- [x] #181 merged / private store usable
- [ ] Human `FREEZE APPROVED` on #196 (regression evidence on final merged `main`)
- [ ] Human partition lock on #197 (embargo **and** completed-monthly warmup acknowledged)
- [ ] Human protocol + decision freeze on #198
- [ ] Human benchmark/regime approval on #199 (metrics 1.2 / Spec cost parity)
- [ ] Private robustness packs for #200–#203 complete (status on issues; metrics private)
- [ ] Forward holdout length ≥ sample-sufficiency min (proposed 90 days) **and** feature warmup satisfied for the evaluation engine
- [ ] Human pre-OOS approval recorded in Decision Log (process only)

## One-shot OOS procedure (when unblocked)

1. Pin public-core SHA in private `PINNED_PUBLIC_CORE.txt`.
2. Publish/bind DatasetManifest covering holdout C only.
3. Run frozen private ExperimentSpec once → `artifacts/research/`.
4. Apply frozen decision rules mechanically.
5. No retune; invalidate + new version if economic bugfix required.

## Final decision (#205)

Private packet under `decisions/`. Public Decision Log records outcome code + issue links **without metrics**. Then close #47.

If forward window is insufficient at first eligibility check → `INCONCLUSIVE` (not ACCEPT).
