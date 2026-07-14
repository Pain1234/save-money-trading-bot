# P3 PR split plan

Issue-scoped stacked branches. Merge train order (rebase onto `main` after each merge):

```
#85 #76 → #86 #77 → #87 #78 → #88 #79 → #89 #80 → (#90 #81 ∥ #91 #83) → #92 #82 → #93 #84
```

## Parallel merge (#81 / #83)

Both branch from `#89` (`p3/80-import-backfill`). Recommended: merge **#91 (#83)** first, then **#90 (#81)**.

## CHANGELOG

Rebase each branch onto updated `main`; keep a single clean `[Unreleased]` block.

## Epic

#45 closes when #84 merges and audit doc is accepted.
