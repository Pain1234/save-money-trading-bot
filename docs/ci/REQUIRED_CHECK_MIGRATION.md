# Required Check Migration: `ci.yml` → `ci-fast.yml` + `ci-full.yml`

**Status:** Phase 1 (compatibility aliases active). See
`docs/branch-protection.md` for the current live branch-protection
configuration.

## Why this exists

GitHub branch protection stores required check **names**, not workflow file
paths. The legacy `ci.yml` reported checks named `validate`,
`requirements-baseline`, `lint`, `test`, `test-market-data`, `test-deploy`,
and `postgres`. Retargeting branch protection to new check names requires an
admin to edit the protected-branch settings — that is a manual, out-of-band
step this PR/worktree cannot perform. Phase 1 exists so **branch protection
does not need to change on day one** of the fast/full split: the same seven
check names keep reporting, just backed by new workflows.

## Phase 1 (current): thin compatibility aliases

`ci-fast.yml` and `ci-full.yml` each define a small number of **real** jobs
(the actual work: `plan`, `quality`, `targeted-tests`, `fast-ci-required` in
the fast lane; `should-run`, `full-quality`, `core-tests`,
`postgres-and-reporting`, `research-repro`, `full-ci-required` in the full
lane) plus a handful of **thin alias jobs** that do no independent work —
they just mirror the pass/fail result of the real gate job under the old
required-check name:

| Legacy required check | Now backed by | Workflow |
|---|---|---|
| `validate` | mirrors `fast-ci-required` | `ci-fast.yml` |
| `requirements-baseline` | mirrors `fast-ci-required` | `ci-fast.yml` |
| `lint` | mirrors `fast-ci-required` | `ci-fast.yml` |
| `test` | mirrors `fast-ci-required` | `ci-fast.yml` |
| `test-market-data` | mirrors `fast-ci-required` | `ci-fast.yml` |
| `test-deploy` | mirrors `full-ci-required` (only when Full CI runs) | `ci-full.yml` |
| `postgres` | mirrors `full-ci-required` (only when Full CI runs) | `ci-full.yml` |

### Important asymmetry: `test-deploy` and `postgres` only report when Full CI runs

The fast-lane aliases (`validate`, `requirements-baseline`, `lint`, `test`,
`test-market-data`) run on **every** `pull_request` event and always report
a result. The full-lane aliases (`test-deploy`, `postgres`) only exist as
jobs when `should-run.outputs.run_full == 'true'` — i.e. push to `main`,
`workflow_dispatch`, a merge-queue run, or a PR carrying the `full-ci`
label.

**Consequence:** on an unlabeled, non-draft-exempt pull request, `postgres`
and `test-deploy` never report a result at all (not "skipped", simply
absent — GitHub Actions does not create the job). Because branch protection
still lists `postgres` and `test-deploy` as required, **the PR cannot merge
until Full CI has run at least once** (add the `full-ci` label, or wait
until the merge to `main`/queue triggers it, depending on how the team
wants Phase 1 enforcement to feel). This is intentional and fail-closed: it
preserves the exact merge gate the old monolithic `ci.yml` provided (every
PR paid for `postgres`/`test-deploy` on every push) without literally
running them on every push.

If this is too strict for your team's workflow, the options are:

1. Add `full-ci` to PRs early and often (cheap if the change is small; the
   label just triggers the heavy suite once, not on every push — Full CI
   still only re-runs on `synchronize` after the label is present, since
   `ci-full.yml`'s `pull_request` trigger includes `synchronize`).
2. Move to Phase 2 (below) and accept that `postgres`/`test-deploy` are no
   longer literally required on every PR — replaced by `full-ci-required`
   which is itself conditionally required.

## Phase 2 (future): retarget branch protection directly

Once the team is comfortable with the fast/full split, an admin should:

1. Open **Settings → Branches → Branch protection rules → `main`**.
2. Remove the legacy required check names: `validate`,
   `requirements-baseline`, `lint`, `test`, `test-market-data`,
   `test-deploy`, `postgres`.
3. Add the new required check names: `plan`, `quality`, `targeted-tests`,
   `fast-ci-required` (fast lane — always required). Whether
   `full-ci-required` should be required directly depends on whether the
   team wants Full CI to gate every merge or only merges that touched
   something Full CI cares about; recommend keeping it **not required** at
   the branch-protection level and instead relying on `fast-ci-required`'s
   fail-closed `run_all_fast` behavior plus periodic/labeled Full CI runs
   for defense in depth.
4. Delete the compatibility alias jobs from `ci-fast.yml` and `ci-full.yml`
   (`validate`, `requirements-baseline`, `lint`, `test`,
   `test-market-data`, `test-deploy`, `postgres`) in the same PR that
   changes branch protection, so there is no window where a required check
   name has no job backing it.
5. Update `docs/branch-protection.md` to reflect the new required check
   list and remove the "Phase 1" language.

Verify the live branch-protection configuration at any time with:

```bash
gh api repos/Pain1234/save-money-trading-bot/branches/main/protection
```

## Rollback

If Stage 2 needs to be rolled back entirely (not just Phase 1 → Phase 2),
see the header comment in `.github/workflows/ci.yml` — it explains how to
restore the full legacy monolithic workflow from git history
(`git show 9acde68:.github/workflows/ci.yml`) rather than reconstructing it
by hand.
