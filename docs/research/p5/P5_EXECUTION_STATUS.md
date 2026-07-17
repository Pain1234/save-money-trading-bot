# P5 Execution Status

**Updated:** 2026-07-17
**Holdout opened?** `NO`

## Wave completion (public core)

| Wave | Issue(s) | Public deliverable | Blocking human / time gate |
|------|----------|--------------------|----------------------------|
| 0 | #181 | Private repo + leakage docs (PR #222) | Merge #222; confirm private ACL |
| 1 | #196 | Candidate freeze prepared (PR #223) | `FREEZE APPROVED` + main SHA |
| 2–4 | #197–#199 | Partitions/protocol/benchmarks proposed (PR #224) | `PARTITIONS LOCKED` / `PROTOCOL FROZEN` / #199 approval |
| 5 | #200–#203 | Robustness helpers (PR #225) | Private B runs after freezes + datasets |
| 6 | #204 | Pre-OOS gate checklist below | All freezes + ≥90d forward window + pre-OOS approval |
| 7 | #205 | Decision template | After #204 once |

## Pre-OOS hard stop (#204)

Do **not** open holdout C until all are true:

- [ ] #181 merged / private store usable
- [ ] Human `FREEZE APPROVED` on #196
- [ ] Human partition lock on #197
- [ ] Human protocol + decision freeze on #198
- [ ] Human benchmark/regime approval on #199
- [ ] Private robustness packs for #200–#203 complete (status on issues; metrics private)
- [ ] Forward holdout length ≥ sample-sufficiency min (proposed 90 days)
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
