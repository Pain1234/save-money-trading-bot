# Branch Protection on `main`

**Issue:** #65
**Branch:** `main` (GitHub default since Issue #64, 2026-07-14)
**Workflows:** `.github/workflows/ci-fast.yml` + `.github/workflows/ci-full.yml`
(Stage 2 fast/full split — see `docs/ci/ACTIONS_OPTIMIZATION_STAGE_2.md`).
`.github/workflows/ci.yml` is now a `workflow_dispatch`-only rollback stub;
it no longer runs on PRs or pushes.

**Migration status: Phase 1.** The required check *names* below are still
the legacy `ci.yml` names. They are currently backed by thin compatibility
alias jobs in `ci-fast.yml`/`ci-full.yml` rather than by real work — see
`docs/ci/REQUIRED_CHECK_MIGRATION.md` for the full migration plan and why
`postgres`/`test-deploy` only report when Full CI actually runs.

## When CI runs

| Event | Runs Fast CI? | Runs Full CI? |
|-------|----------|----------|
| `pull_request` targeting `main` (opened/reopened/synchronize/ready_for_review) | Yes (cancel-in-progress on new commits) | Only if the PR has the `full-ci` label |
| `pull_request` labeled/unlabeled | No (not a fast-lane trigger) | Yes for `labeled`/`unlabeled` (re-evaluates `should-run`) |
| `push` to `main` | No (not a fast-lane trigger) | Yes |
| `workflow_dispatch` | Yes (manual) | Yes (manual) |
| Merge queue (`merge_group`) | No | Yes |
| Push to a feature branch | No (use the open PR against `main`) | No |
| Docs-only PR (only `*.md` / `docs/**` / license noise, no governance path) | `plan` only; `quality`/`targeted-tests` skip and count as passing | Unaffected by diff shape — still gated on the `full-ci` label |

Within Fast CI, the diff is further classified by
`scripts/ci/classify_paths.py` to decide *which* test slices actually run
(e.g. a `services/research/**`-only change only runs the research slice,
not the full fast-lane suite). See
`docs/ci/ACTIONS_OPTIMIZATION_STAGE_2.md` for the fail-closed rules.

## Required status checks (Phase 1 — legacy names, new backing)

These job `name` values must still pass before merging a PR into `main`.
During Phase 1 they are reported by thin alias jobs; see
`docs/ci/REQUIRED_CHECK_MIGRATION.md` before changing this list.

| Check | Backed by (Phase 1) | Purpose |
|-------|-----|---------|
| `validate` | `ci-fast.yml` → mirrors `fast-ci-required` | Python compile, issue templates, governance tests, PR whitespace |
| `requirements-baseline` | `ci-fast.yml` → mirrors `fast-ci-required` | Portable `requirements-baseline.txt` install |
| `lint` | `ci-fast.yml` → mirrors `fast-ci-required` | `ruff check .` |
| `test` | `ci-fast.yml` → mirrors `fast-ci-required` | Unit tests (excludes deploy, postgres, live, soak) |
| `test-market-data` | `ci-fast.yml` → mirrors `fast-ci-required` | `tests/market_data -m "not live"` |
| `test-deploy` | `ci-full.yml` → mirrors `full-ci-required`, **only reports when Full CI ran** | Dashboard build + bundle checks (Node 22) |
| `postgres` | `ci-full.yml` → mirrors `full-ci-required`, **only reports when Full CI ran** | PostgreSQL integration tests (`-m "postgres and not soak"`) |

**Practical consequence:** an unlabeled PR never gets a `test-deploy` or
`postgres` result, so it cannot merge until the `full-ci` label is added at
least once (or the branch is otherwise routed through a Full CI run). This
is intentional and documented in `docs/ci/REQUIRED_CHECK_MIGRATION.md`.

**Not required:** `plan`, `quality`, `targeted-tests`, `fast-ci-required`,
`should-run`, `full-quality`, `core-tests`, `postgres-and-reporting`,
`research-repro`, `full-ci-required` — the *real* Stage 2 job names are not
yet wired into branch protection (Phase 2). `research-repro` was never
required even under the legacy workflow. `github-governance-setup.yml`
`validate` remains a path-filtered governance dry-run, not required.

## Protection rules

| Rule | Setting |
|------|---------|
| Require pull request before merging | Yes |
| Required status checks | All seven CI checks above |
| Require branches to be up to date | Yes (strict) |
| Required reviewers | None (solo maintainer per ADR-011) |
| Allow admin bypass | Yes (maintainer emergency merge) |

## Solo-maintainer review (ADR-011)

Self-review on PR is acceptable when CI is green and scope matches a linked issue.
Merge is blocked when any required check fails.

## Verify settings

```bash
gh api repos/Pain1234/save-money-trading-bot/branches/main/protection
```
