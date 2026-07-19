# P5 Phase 3 — Cross-Check Receipt (technical only)

**Date (UTC):** 2026-07-19
**Holdout:** `SEALED` / unopened
**Economic accept/reject:** **NOT decided** (human #205 only)

This document records technical integrity checks only. It contains **no**
PnL, drawdown, trade lists, or other private economic metrics.

## Binding pins

| Field | Value |
|-------|-------|
| `public_core_sha` | `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4` |
| `symbol_constraints_hash` | `e5b2254249179eebe89d8d349b2a44566b50fbe79b37b2f32b62dc8d3b364817` |
| `constraint_set_version` | `hl-mainnet-szdecimals-v1` |
| `strategy_id` / `strategy_version` | `trend_v1` / `1.0.0` |
| Shared base `run_id` | `run_d46385969c40bf62cc1468b61a6b889f16137d11779fce83300f68e1cae84de0` |
| Candidate freeze hash | `90214c9031ccc91091a24a171991fbf84032c45845154cd78b4350ed0bfb59d6` |

## Pack inventory (ids only)

| Issue | Type | Status | Robustness id |
|-------|------|--------|---------------|
| #251 | walk_forward | complete (3/3 folds) | `rob_bc10d428e00e901e88ffe9edafd8113f3b6b7060b1011aad20f3d5139a7a84d0` |
| #252 | cost_stress | complete (6/6 scenarios) | `rob_dc59e2b36911a1c3d6fcec21c58d12399ea5ee6d03d2c4eaeba2393390de2dd9` |
| #253 | parameter_stability | complete (frozen + 12 neighbors) | `rob_ad265f36d055ccbd49c9820d7a7b457b2ffdd44e55b778b69df61a54f214fc68` |
| #254 | bootstrap | complete (block=5, n=1000, seed=42) | `rob_a3eedf6f5def684e178cc6a2a9280fe9158c50936058d2272247763eeb0dd20a` |

Private store: `Pain1234/save-money-trading-bot-private-research` (PRs #2–#5 merged).

## Agent 1 integrity (automated)

Automated check script over private pack summaries + per-child `checksums.json` /
`run_manifest.json` / sealed `symbol_constraints` presence:

- **130 PASS / 0 FAIL** (2026-07-19)

Covered: pin match, constraint hash, strategy version, git commit pin, child
completeness, robustness manifest + sha256 sidecar, shared base run, reproduction
files present.

## Agent 2 → Agent 3 checks

- [x] Parameter neighborhood includes explicit `frozen` child
- [x] Exactly 12 `neighbor_*` children (no grid expansion)
- [x] Seed/method for #254 match freeze plan (block 5 / 1000 / seed 42)
- [x] No candidate replacement indicated in public status artifacts

## Agent 3 → Agent 2 checks

- [x] Walk-forward folds `fold_01`..`fold_03` all present/complete
- [x] No fold dropped from pack summary
- [x] Cost scenarios complete set: base, fee_x2, slippage_x2, funding_stress,
      combined_elevated, combined_extreme
- [x] Same public-core / constraint / base run pins as #251

## Leakage / holdout

- [x] Public issues contain status + ids only (no private metrics in comments reviewed for #251–#254)
- [x] Holdout remains `SEALED`
- [x] Pre-#363 packs remain invalidated

## Outcome of Phase 3

**TECHNICALLY CLEAR for Pre-OOS human gate.**
Does **not** authorize #204 execution until human Pre-OOS approval is recorded.
