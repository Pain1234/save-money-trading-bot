# P5 Execution Status

**Updated:** 2026-07-19
**Holdout opened?** `NO`

## Wave completion (public core)

One GitHub issue per branch/PR (AGENTS.md / DoD). No silent multi-issue bundling.

| Wave | Issue | Public deliverable | Blocking human / time gate |
|------|-------|--------------------|----------------------------|
| 0 | #181 | Private repo + leakage docs | **Merged** (PR #222); confirm private ACL |
| 1 | #196 | Candidate freeze evidence on main tip | Human `FREEZE APPROVED` + pin SHA + UTC (evidence refreshed) |
| 2 | #197 | Partitions / exposure audit | `PARTITIONS LOCKED` + embargo + monthly warmup ack |
| 3 | #198 | Protocol + decision rules | `PROTOCOL FROZEN` / `DECISION RULES FROZEN` |
| 4 | #199 | Benchmarks / regimes | Human approval (metrics 1.2 / Spec cost parity) |
| 4b | #294 | Scorecard/policy version bind | Human `SCORECARD POLICY BIND FROZEN` (Holdout stays closed) |
| 5a | #200 | Walk-forward helper | Private B runs after freezes |
| 5b | #201 | Cost-stress scenarios | Private B runs after freezes |
| 5c | #202 | Parameter neighborhood | Private B runs after freezes |
| 5d | #203 | Path bootstrap helper | Private B runs after freezes |
| 6 | #204 | Pre-OOS gate checklist below | All freezes + sufficiency + pre-OOS approval |
| 7 | #205 | Decision process / ADR | After #204 once |

## Pre-OOS hard stop (#204)

Do **not** open holdout C until all are true:

- [x] #181 merged / private store usable
- [x] Human `FREEZE APPROVED` on #196 (comment 2026-07-19T12:54:01Z; pin SHA `35b4fa6d0c7d4f74a397a7d1a57437823341237b` — **note:** `main` tip has advanced; refresh freeze pin after #363 merge before #251)
- [x] Human partition lock on #197 (`PARTITIONS LOCKED` 2026-07-19T12:54:01Z)
- [x] Human protocol + decision freeze on #198 (`PROTOCOL FROZEN` / `DECISION RULES FROZEN`)
- [x] Human benchmark/regime approval on #199 (`BENCHMARKS AND REGIMES APPROVED`)
- [x] Human scorecard/policy bind sign-off on #294 (`SCORECARD POLICY BIND FROZEN`; Holdout remains closed)
- [ ] #363 sealed symbol constraints merged on `main` (prior private Partition B packs invalidated)
- [ ] Private robustness packs for #251–#254 complete (status on issues; metrics private)
- [ ] Forward holdout length ≥ sample-sufficiency min (proposed 90 days) **and** feature warmup satisfied for the evaluation engine
- [ ] Human pre-OOS approval recorded in Decision Log (process only)

## Symbol-constraint seal (#363) — private pack invalidation

P5 Partition B private executions that ran **before** sealed
`ExperimentSpec.symbol_constraints` (Hyperliquid szDecimals v1 pins wired into
`BacktestConfig` / Spec identity) are **technically invalidated**. Do not treat
those packs as evidence for #251–#254.

- Re-run only after this fix is on `main` and the public-core SHA is pinned.
- Holdout remains closed (`NO`); no Strategy V1 parameter changes in #363.
- Constraint set version: `hl-mainnet-szdecimals-v1` (BTC=5 / ETH=4 / SOL=2).

## Gate status snapshot (2026-07-19, post #250 acceptance evidence)

| Gate | State |
|------|-------|
| Public stack #181 / #196-docs / #197-#203 / #204-prep / #205-prep | On `main` |
| Human locks #196–#199 + #294 | **Present** (see comments; freeze pin SHA may need refresh vs tip) |
| #250 P4 acceptance evidence | Recorded on `1516ddb…`; **human close pending** |
| #363 sealed symbol constraints | **Required before valid #251–#254 re-runs**; prior private packs invalidated |
| Private Partition B datasets | **Missing** (templates only) |
| Private robustness packs #200-#203 helpers | On `main`; **execution packs not run** |
| Next Ready (after #363 merge + human #250/#295 close) | [#251](https://github.com/Pain1234/save-money-trading-bot/issues/251) private Walk-Forward — **do not start in this PR** |
| Forward holdout length | **Not started** |
| Holdout opened? | `NO` |
| #204 OOS execution | **BLOCKED** — do not run |
| #205 final decision | **BLOCKED** by #204 |
| #47 | Remains open until #205 |

## One-shot OOS procedure (when unblocked)

1. Pin public-core SHA in private `PINNED_PUBLIC_CORE.txt`.
2. Publish/bind DatasetManifest covering holdout C only.
3. Run frozen private ExperimentSpec once → `artifacts/research/`.
4. Apply frozen decision rules mechanically.
5. No retune; invalidate + new version if economic bugfix required.

## Final decision (#205)

Private packet under `decisions/`. Public Decision Log records outcome code + issue links **without metrics**. Then close #47.

If forward window is insufficient at first eligibility check → `INCONCLUSIVE` (not ACCEPT).
