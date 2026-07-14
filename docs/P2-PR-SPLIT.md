# P2 PR split plan

Issue-scoped branches (local). **Do not push until CHANGELOG UTF-8 verified.**

## Merge order

1. #16 `p2/16-metrics`
2. #13 `p2/13-idempotency-audit`
3. #14 `p2/14-worker-restart`
4. #12 `p2/12-reconciliation`
5. #15 `p2/15-runbooks-index`

**Not in initial merge train:** #11 `p2/11-backup-restore-draft` — open as **draft PR only**;
merge after restore drill. Then update runbook index and ROADMAP.

## Rebase rule

Each branch changes `[Unreleased]` in CHANGELOG.md. After merging a PR, rebase the next branch
onto updated `main` and verify CHANGELOG has a single clean `[Unreleased]` block (no duplicate
`### Changed` under historical releases).

## Issue #15 bundling (document in PR body)

Bundles `deployment-verify`, `worker-safe-stop`, and `kill-switch` runbooks with index and
tabletop incident. Deviation from one-PR-per-runbook: index/tabletop require one pass.

## Backup runbook dependency

Issue #15 index lists backup as **TODO / Issue #11** until the draft PR merges post-drill.
