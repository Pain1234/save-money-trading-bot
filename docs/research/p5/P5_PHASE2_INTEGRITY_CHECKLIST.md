# P5 Phase 2 — Agent 1 Integrity Checklist

**Role:** Agent 1 (Public Core / Freeze Guardian) — read-only over private result
artifacts; no mutation of Agent 2/3 packs.

**Binding pin:** `aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4`
**Docs tip:** `8bb39c165973b00170f78ce580a211e7a1e6d9e8`
**Holdout:** `SEALED`

Use after each of #251–#254 reports completion (private artifacts sealed).

## Per-run checks

| Check | #251 | #252 | #253 | #254 |
|-------|------|------|------|------|
| `PINNED_PUBLIC_CORE` == `aa0e232…` | | | | |
| Spec schema `1.0` | | | | |
| `symbol_constraints_hash` == `e5b22542…` | | | | |
| `strategy_id` / `strategy_version` == `trend_v1` / `1.0.0` | | | | |
| `candidate_freeze_hash` == `90214c90…` | | | | |
| Dataset manifest pin present + hash match | | | | |
| Artifact checksums present + verified | | | | |
| Reproduction command documented | | | | |
| Evidence-completeness status recorded | | | | |
| No private metrics in public issue/PR | | | | |
| Holdout still sealed | | | | |

## Cross-run consistency

- [ ] Same public-core SHA on all four packs
- [ ] Same constraint hash on all four packs
- [ ] Same candidate freeze hash on all four packs
- [ ] No unexplained Spec / config mutation between packs
- [ ] #252 uses same candidate + dataset pins as #251
- [ ] #254 uses same candidate as #253 (no replacement)

## Fail closed

Any mismatch → mark pack **technically invalidated**; do not start #204; open
a public-core or private integrity issue without leaking metrics.
