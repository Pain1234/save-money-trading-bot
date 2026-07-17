# GitHub Actions Optimization — Stage 2 (Fast/Full CI Split)

**Follows:** Stage 1 (`0306a56`, "Reduce GitHub Actions usage without
dropping required CI checks" — concurrency cancellation, pip caching,
timeouts, docs-only path filter).

**Goal:** stop running the entire heavy test matrix (Postgres integration,
research double-run reproducibility, dashboard build) on every PR push when
the diff could not possibly affect those areas, without weakening the merge
gate on `main`. See `docs/ci/ACTIONS_USAGE_BASELINE.md` for the before/after
cost model and `docs/ci/REQUIRED_CHECK_MIGRATION.md` for how required
checks migrate without an immediate branch-protection edit.

## What changed

Three workflows replace the single monolithic `ci.yml`:

| Workflow | Triggers | What it does |
|---|---|---|
| `ci-fast.yml` | Every `pull_request` push, `workflow_dispatch` | Classifies the diff, runs only the quality/test slices implied by what changed. Always finishes in minutes. |
| `ci-full.yml` | `push` to `main`, `workflow_dispatch`, `merge_group`, or a PR carrying the `full-ci` label | The full heavy suite: Postgres integration, perf/reporting, research reproducibility gate, dashboard build. |
| `ci.yml` | `workflow_dispatch` only (with a confirmation input) | Rollback stub. Does not run any tests; points at git history to restore the old monolithic job set if Stage 2 needs to be reverted wholesale. |

### `ci-fast.yml` jobs

1. **`plan`** — runs `scripts/ci/classify_paths.py` against the PR diff
   (stdlib only, no `pip install`) and emits ~18 boolean routing flags as
   job outputs (`docs_only`, `research`, `market_data`, `run_all_fast`,
   etc.). Always fail-closed: anything the classifier cannot confidently
   place (unknown path, empty diff, multiple service areas touched in one
   diff, an internal error) sets `run_all_fast=true`, which makes
   downstream jobs run the full fast-lane suite instead of a narrow slice.
2. **`quality`** — conditional on `run_quality`/`governance`/`workflows`/
   `dependencies`. Runs `compileall`, issue-template validation, governance
   unit tests, the requirements-baseline sanity check, and `ruff check .`,
   each gated independently so a governance-only doc change (e.g.
   `docs/branch-protection.md`) doesn't pay for a full `pip install -e
   ".[dev]"` just to run three stdlib-only governance tests.
3. **`targeted-tests`** — conditional on `run_targeted_tests` (i.e. not a
   pure docs-only diff). Runs the pytest slice(s) matching whichever
   service-area flags are set (`research`, `market_data`, `paper_trading`,
   `backtest`+`strategy`, `risk`, `deploy`), or the entire
   fast-lane suite when `run_all_fast` is set.
4. **`fast-ci-required`** — the actual merge gate. Uses
   `scripts/ci/check_required_gate.py` to verify `plan` succeeded, and that
   `quality`/`targeted-tests` are `success` when they were expected to run
   or `skipped` when they were legitimately not needed. `cancelled` is
   never acceptable, regardless of configuration.
5. Five thin **Phase-1 compatibility alias jobs** (`validate`,
   `requirements-baseline`, `lint`, `test`, `test-market-data`) that mirror
   `fast-ci-required`'s result under the legacy required-check names. See
   `docs/ci/REQUIRED_CHECK_MIGRATION.md`.

### `ci-full.yml` jobs

1. **`should-run`** — decides whether Full CI should actually execute:
   `true` for `push`/`workflow_dispatch`/`merge_group`, and for
   `pull_request` only when the PR carries the **`full-ci`** label.
2. **`full-quality`**, **`core-tests`**, **`postgres-and-reporting`**,
   **`research-repro`** — the exact same commands as the old `ci.yml`'s
   `validate`+`lint`+`requirements-baseline`, `test`+`test-market-data`+
   `test-deploy`, `postgres`+`perf-reporting`, and `research-repro` jobs,
   respectively, gated on `should-run`.
3. **`full-ci-required`** — gate job. When `should-run` says no, this
   succeeds immediately with a "Full CI not requested" message (no heavy
   jobs ran, and that's expected). When `should-run` says yes, it requires
   all four heavy jobs to succeed.
4. Two thin compatibility alias jobs (`test-deploy`, `postgres`) that only
   exist (and only report) when Full CI actually ran. **This is the one
   place Phase 1 changes merge behavior on unlabeled PRs** — see
   `docs/ci/REQUIRED_CHECK_MIGRATION.md` for why that's intentional.

## Using the `full-ci` label

Add the `full-ci` label to a pull request to opt it into the heavy suite on
its next push (the label-add itself also triggers a run, via the `labeled`
event type). Remove the label (`unlabeled` event) if you want to stop
paying for Full CI on further pushes to that PR — existing check results
are not retroactively invalidated, but no new Full CI run will be queued
until the label is re-added or another qualifying event (push to `main`,
merge queue) happens.

```bash
# Add the label to opt a PR into Full CI on its next push
gh pr edit <PR_NUMBER> --add-label full-ci

# Remove it once you're back to fast-lane-only iteration
gh pr edit <PR_NUMBER> --remove-label full-ci
```

If the `full-ci` label does not exist yet in the repository, create it once:

```bash
gh label create full-ci \
  --description "Opt this PR into the full CI suite (Postgres, research repro, dashboard build)" \
  --color BFA5FF
```

Recommended usage: keep PRs on fast-lane-only iteration while developing,
add `full-ci` before requesting review (or right before merge) so the heavy
suite has run at least once on the final diff.

## Fail-closed classification: `scripts/ci/classify_paths.py`

The classifier is deliberately conservative. Any of the following forces
`run_all_fast=true` (the fast lane then runs its entire non-heavy suite
instead of a narrow slice):

- The diff is empty, or the classifier hit an internal error.
- Any changed path doesn't match a known category *and* isn't a
  docs-only candidate (e.g. a new top-level config file, a `.cursor/`
  path).
- `pyproject.toml`, lock files, or any `requirements*.txt` changed
  (`dependencies`).
- Anything under `.github/workflows/**` changed (`workflows`).
- A "shared" path changed: `tests/conftest.py`, `tests/fixtures/**`,
  `tests/postgres_fixtures.py`, `tests/e2e/**`, or any `scripts/*.py`
  other than `scripts/github_project_setup.py` (`shared_python`).
- A database-adjacent path changed: `alembic/**`, `**/migrations/**`, or
  any path containing `postgres` (`database`).
- **Two or more distinct service areas** (`research`, `market_data`,
  `paper_trading`, `backtest`, `strategy`, `risk`) are touched in the same
  diff — the classifier does not try to guess a safe combined test slice
  for cross-service changes.

Docs-only diffs (every changed path is `*.md`, `docs/**`, `LICENSE*`,
`.gitignore`, an image under `docs/`, or a `.gitkeep`) are the one
fail-**open** case: `quality` and `targeted-tests` are skipped entirely,
unless the diff also matches a governance path (e.g.
`docs/branch-protection.md`), in which case `quality` still runs the
lightweight, stdlib-only governance checks.

See `tests/ci/test_classify_paths.py` for the full behavioral contract
(one test per rule above, plus multi-service and empty-diff cases), and
`tests/ci/test_workflow_routing_contract.py` for structural assertions
about the workflow YAML itself (concurrency groups, permissions, no
self-hosted runners, exact command parity with the old `ci.yml` for the
Full CI jobs, required job names).

## Rollback

`.github/workflows/ci.yml` is now a `workflow_dispatch`-only stub that
refuses to run anything unless given an explicit confirmation string, and
its header comment documents exactly how to restore the full legacy
monolithic workflow from git history if Stage 2 needs to be reverted
wholesale rather than fixed forward.
