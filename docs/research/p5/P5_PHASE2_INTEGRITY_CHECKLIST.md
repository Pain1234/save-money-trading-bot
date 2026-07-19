# P5 Phase 2 — Agent 1 Integrity Checklist

**Role:** Agent 1 (Public Core / Freeze Guardian) — read-only over private result
artifacts; no mutation of Agent 2/3 packs.

**Binding pin:** `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4`
**Docs tip:** `8bb39c165973b00170f78ce580a211e7a1e6d9e8` (later docs merges OK)
**Holdout:** `SEALED`
**Phase-3 result:** **130 PASS / 0 FAIL** (2026-07-19) — see `P5_PHASE3_CROSS_CHECK.md`

## Per-run checks

| Check | #251 | #252 | #253 | #254 |
|-------|------|------|------|------|
| `PINNED_PUBLIC_CORE` == `aa0e232…` | x | x | x | x |
| Spec schema `1.0` | x | x | x | x |
| `symbol_constraints_hash` == `e5b22542…` | x | x | x | x |
| `strategy_id` / `strategy_version` == `trend_v1` / `1.0.0` | x | x | x | x |
| Shared base run pin | x | x | x | x |
| Dataset manifest pin present | x | x | x | x |
| Artifact checksums present + verified | x | x | x | x |
| Reproduction command documented | x | x | x | x |
| Evidence-completeness status recorded | x | x | x | x |
| No private metrics in public issue/PR | x | x | x | x |
| Holdout still sealed | x | x | x | x |

## Cross-run consistency

- [x] Same public-core SHA on all four packs
- [x] Same constraint hash on all four packs
- [x] Same shared base `run_id` across packs
- [x] No unexplained Spec / config mutation between packs
- [x] #252 uses same candidate + dataset pins as #251
- [x] #254 uses same base as #251/#253 (no candidate replacement)

## Fail closed

Any mismatch → mark pack **technically invalidated**; do not start #204; open
a public-core or private integrity issue without leaking metrics.
