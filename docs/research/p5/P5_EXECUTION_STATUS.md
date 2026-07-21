# P5 Execution Status

**Authority:** This document is the single public Source of Truth for current P5
phase and gate status. Other files in this directory define frozen contracts,
checklists, or historical handoffs; their header status must not override this
ledger.
**Updated:** 2026-07-21 (AUD-P2-008 reconciliation; no new execution)
**Holdout opened?** `NO`
**Current phase:** **PRE-OOS BLOCKED** — prerequisite robustness executions are
complete, but P5 itself is not complete and no final decision exists.

## Authoritative public narrative

- [#196](https://github.com/Pain1234/save-money-trading-bot/issues/196):
  candidate freeze approved and pin refreshed. The issue remaining open does not
  mean the freeze is unsigned.
- [#251](https://github.com/Pain1234/save-money-trading-bot/issues/251),
  [#252](https://github.com/Pain1234/save-money-trading-bot/issues/252),
  [#253](https://github.com/Pain1234/save-money-trading-bot/issues/253), and
  [#254](https://github.com/Pain1234/save-money-trading-bot/issues/254):
  sealed pre-OOS robustness executions are complete and technically
  cross-checked. Their economic results remain private; completion is neither an
  OOS result nor a promotion decision.
- [#204](https://github.com/Pain1234/save-money-trading-bot/issues/204):
  final untouched OOS has **not** run. The holdout remains sealed and execution
  is blocked by the forward-window, warmup, and human Pre-OOS gates below.
- [#205](https://github.com/Pain1234/save-money-trading-bot/issues/205):
  no `ACCEPT_FOR_P6`, `REJECT`, or `INCONCLUSIVE` decision has been recorded;
  this remains blocked by #204.

GitHub issue open/closed state is workflow metadata, not evidence that an
execution or gate is incomplete. The status above is supported only by the
linked public comments and public, non-economic receipts. No private economic
metric is reproduced here.

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
| 6 | #204 | Pre-OOS gate checklist | Docs merged (PR #369); **awaiting human `PRE-OOS APPROVED` + ≥90d forward window** — see `P5_PRE_OOS_GATE.md` |
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
- [ ] Forward holdout length ≥ sample-sufficiency min (90 calendar days per frozen protocol) **and** feature warmup satisfied for the evaluation engine
- [ ] Human pre-OOS approval recorded (`PRE-OOS APPROVED` on #204 + Decision Log process note)

### Forward-holdout calendar (status only — no metrics)

| Field | Value |
|-------|-------|
| Holdout clock start (Candidate Freeze UTC) | `2026-07-19T12:54:01Z` (`FREEZE APPROVED` on #196 @ `35b4fa6…`) |
| Pin refresh does **not** reset clock | `FREEZE PIN REFRESHED` 2026-07-19T15:47:02Z on `aa0e232…` |
| Status check UTC | `2026-07-19` |
| Elapsed forward calendar days | **~0** (same UTC day as freeze) |
| Earliest day min-duration (90d) can pass | **≥ `2026-10-17T12:54:01Z`** |
| Verdict at this check | **NOT MET** — #204 one-shot OOS remains calendar-blocked |

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
| Pre-OOS checklist docs | **Merged** PR #369 → `c469b65…` |
| Sample-sufficiency (90d) | **NOT MET** (~0d elapsed; earliest ~2026-10-17) |
| Holdout opened? | `NO` / `SEALED` |
| #204 OOS execution | **BLOCKED** on `PRE-OOS APPROVED` + ≥90d forward window + warmup ack |
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
