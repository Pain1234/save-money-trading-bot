# P5 Execution Status

**Updated:** 2026-07-19
**Holdout opened?** `NO`

## Wave completion (public core)

One GitHub issue per branch/PR (AGENTS.md / DoD). No silent multi-issue bundling.

| Wave | Issue | Public deliverable | Blocking human / time gate |
|------|-------|--------------------|----------------------------|
| 0 | #181 | Private repo + namespace docs | **Merged** (PR #222); confirm private ACL |
| 1 | #196 | Candidate freeze evidence on main tip | **`FREEZE PIN REFRESHED`** 2026-07-19T15:47:02Z on `aa0e232…` |
| 2 | #197 | Partitions / exposure audit | `PARTITIONS LOCKED` + embargo + monthly warmup ack |
| 3 | #198 | Protocol + decision rules | `PROTOCOL FROZEN` / `DECISION RULES FROZEN` |
| 4 | #199 | Benchmarks / regimes | Human approval (metrics 1.2 / Spec cost parity) |
| 4b | #294 | Scorecard/policy version bind | Human `SCORECARD POLICY BIND FROZEN` (Holdout stays closed) |
| 5a | #200 | Walk-forward helper | Helpers on `main`; execution = #251 |
| 5b | #201 | Cost-stress scenarios | Helpers on `main`; execution = #252 |
| 5c | #202 | Parameter neighborhood | Helpers on `main`; execution = #253 |
| 5d | #203 | Path bootstrap helper | Helpers on `main`; execution = #254 |
| 6 | #204 | Pre-OOS gate checklist | **Awaiting human `PRE-OOS APPROVED`** — see `P5_PRE_OOS_GATE.md` |
| 7 | #205 | Decision process / ADR | After #204 once |

## Pre-OOS hard stop (#204)

Do **not** open holdout C until all are true:

- [x] #181 merged / private store usable
- [x] Human `FREEZE APPROVED` on #196 (prior pin `35b4fa6…` @ 2026-07-19T12:54:01Z)
- [x] Human `FREEZE PIN REFRESHED` on #196 for public-core `aa0e232…` (2026-07-19T15:47:02Z)
- [x] Human partition lock on #197 (`PARTITIONS LOCKED` 2026-07-19T12:54:01Z)
- [x] Human protocol + decision freeze on #198 (`PROTOCOL FROZEN` / `DECISION RULES FROZEN`)
- [x] Human benchmark/regime approval on #199 (`BENCHMARKS AND REGIMES APPROVED`)
- [x] Human scorecard/policy bind sign-off on #294 (`SCORECARD POLICY BIND FROZEN`; Holdout remains closed)
- [x] #363 sealed symbol constraints merged on `main` (PR #366 @ `aa0e232…`; prior private Partition B packs invalidated)
- [x] Private robustness packs #251–#254 complete on sealed SHA (private PRs #2–#5; Phase-3 cross-check **130/0**)
- [ ] Forward holdout length ≥ sample-sufficiency min (proposed 90 days) **and** feature warmup satisfied for the evaluation engine
- [ ] Human pre-OOS approval recorded (`PRE-OOS APPROVED` on #204 + Decision Log process note)

## Symbol-constraint seal (#363) — private pack invalidation

P5 Partition B private executions that ran **before** sealed
`ExperimentSpec.symbol_constraints` are **technically invalidated**.

- Constraint set: `hl-mainnet-szdecimals-v1` (BTC=5 / ETH=4 / SOL=2).
- **Merged:** PR #366 → `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4`.
- Gate-1 handoff: `docs/research/p5/P5_GATE1_HANDOFF.md`.

## Gate status snapshot (2026-07-19, post Phase 3)

| Gate | State |
|------|-------|
| #363 sealed constraints | **Merged** `aa0e232…` |
| Gate 1 | **Complete** |
| #251–#254 sealed re-runs | **Complete** (private PRs #2–#5 merged) |
| Phase 3 cross-check | **PASS** (130/0) — `P5_PHASE3_CROSS_CHECK.md` |
| Pre-OOS checklist | **Ready for human** — `P5_PRE_OOS_GATE.md` |
| Holdout opened? | `NO` / `SEALED` |
| #204 OOS execution | **BLOCKED** on human `PRE-OOS APPROVED` + sample-sufficiency ack |
| #205 final decision | **BLOCKED** by #204 |
| #47 | Remains open until #205 |

## One-shot OOS procedure (when unblocked)

1. Human `PRE-OOS APPROVED` on #204 with SHA + UTC.
2. Confirm sample-sufficiency / warmup for holdout C.
3. Pin public-core SHA in private `PINNED_PUBLIC_CORE.txt` (already `aa0e232…` unless tip moves with approved re-pin).
4. Publish/bind DatasetManifest covering holdout C only.
5. Run frozen private ExperimentSpec **once** → `artifacts/research/`.
6. Apply frozen decision rules mechanically.
7. No retune; invalidate + new version if economic bugfix required.

## Final decision (#205)

Private packet under `decisions/`. Public Decision Log records outcome code + issue links **without metrics**. Then close #47.

If forward window is insufficient at first eligibility check → `INCONCLUSIVE` (not ACCEPT).
