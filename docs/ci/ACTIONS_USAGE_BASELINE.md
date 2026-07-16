# GitHub Actions Usage Baseline (pre Stage 2)

**Purpose:** record what the monolithic `ci.yml` cost in Actions minutes
before the Stage 2 fast/full split, so the Stage 2 savings claim
(`docs/ci/ACTIONS_OPTIMIZATION_STAGE_2.md`) has a documented before/after
comparison instead of an unverifiable "it's faster now" assertion.

## Caveat: this is a structural estimate, not queried billing data

This document was produced from a repository worktree with **no live GitHub
API/billing access** (no `gh auth`, no org billing scope available in this
session). Every number below is derived from the job definitions in the old
`.github/workflows/ci.yml` (`timeout-minutes` ceilings, `runs-on` labels, and
service containers) plus what the Stage 1 commit message
(`0306a56`, "Reduce GitHub Actions usage without dropping required CI
checks") describes. **These are structural upper bounds, not measured
wall-clock or billed minutes.** Real jobs almost always finish well under
their `timeout-minutes` ceiling.

Before trusting a specific minutes-saved number in a PR description or
external report, a maintainer with repo/org access must pull the real
numbers:

```bash
# Per-run timing (billable minutes per job, per run) for the most recent runs
# of a given workflow file:
gh api repos/Pain1234/save-money-trading-bot/actions/workflows/ci.yml/runs \
  --paginate --jq '.workflow_runs[] | {id, status, conclusion, created_at}' \
  | head -50

# Billable minutes for one specific run (breaks down by runner OS):
gh api repos/Pain1234/save-money-trading-bot/actions/runs/<RUN_ID>/timing

# Repo-level Actions minutes used this billing cycle (requires admin on the
# repo or org, and only works for orgs/users with a billing plan that
# exposes this endpoint):
gh api repos/Pain1234/save-money-trading-bot/actions/settings \
  2>/dev/null || echo "no repo-level usage endpoint; try the org/user endpoint below"
gh api orgs/Pain1234/settings/billing/actions        # if Pain1234 is an org
gh api users/Pain1234/settings/billing/actions       # if Pain1234 is a personal account
```

Re-run the `.../actions/runs/<RUN_ID>/timing` query against a handful of
recent `ci-fast.yml` and `ci-full.yml` runs after Stage 2 has been live for
a week or two, and update this document (or a follow-up
`ACTIONS_USAGE_STAGE_2_MEASURED.md`) with the real deltas.

## Structural inventory: legacy `ci.yml` (pre Stage 2)

Every one of these jobs ran on **every** `pull_request` and `push` to
`main` that touched any non-docs file (Stage 1's `changes` job only skipped
docs-only diffs). All ran in parallel (each on its own `ubuntu-latest`
runner), so wall-clock time for the PR check was bounded by the slowest job,
but **billed Actions minutes are summed across every job**, not just the
critical path.

| Job | `timeout-minutes` (ceiling) | Runner | Notes |
|---|---|---|---|
| `changes` | 5 | ubuntu-latest | Path-filter only, cheap |
| `validate` | 10 | ubuntu-latest | compileall, issue templates, governance tests |
| `requirements-baseline` | 15 | ubuntu-latest | Builds a throwaway venv, installs from lock file |
| `lint` | 10 | ubuntu-latest | `pip install -e ".[dev]"` + ruff |
| `test` | 20 | ubuntu-latest | Full non-postgres unit suite |
| `research-repro` | 20 | ubuntu-latest | Research + parity + double-run gate |
| `test-market-data` | 15 | ubuntu-latest | market_data suite |
| `test-deploy` | 20 | ubuntu-latest | Node 22 + npm ci + dashboard build |
| `postgres` | 25 | ubuntu-latest, `postgres:16-alpine` service | Postgres integration suite |
| `perf-reporting` | 25 | ubuntu-latest, `postgres:16-alpine` service | Perf/reporting tests + artifact upload |
| **Total ceiling** | **165 minutes/run** | — | Sum of all job ceilings; **not** a wall-clock time |

Ten jobs ran on **every** code-touching PR push, regardless of whether the
change touched research, the dashboard, risk limits, or a single docstring
in `services/market_data`. That is the core inefficiency Stage 2 addresses:
the diff shape did not change which jobs ran, only whether they ran at all
(docs-only vs. everything-else).

## Structural inventory: Stage 2 fast lane (`ci-fast.yml`)

Per PR push, `plan` always runs (cheap, stdlib-only classification). Beyond
that, only the slices implied by the diff run:

| Scenario | Jobs that actually execute | Rough ceiling |
|---|---|---|
| Docs-only PR | `plan` only (quality/targeted-tests skip) | 5 min |
| Single-service change (e.g. `services/research/**` only) | `plan`, `quality`, `targeted-tests` (research slice), `fast-ci-required` | ~5 + 10 + 15 + 5 = 35 min |
| Dependency/workflow/shared-python change (`run_all_fast`) | `plan`, `quality`, `targeted-tests` (full fast suite), `fast-ci-required` | ~5 + 10 + 15 + 5 = 35 min |
| Every scenario also pays the 5 thin Phase-1 compatibility aliases (`validate`, `requirements-baseline`, `lint`, `test`, `test-market-data`), each ≤ 5 min and doing no real work | +5 jobs × ≤5 min ceiling, seconds in practice | +25 min ceiling, negligible actual |

Even in the worst case (`run_all_fast`, every compatibility alias present),
the fast lane's ceiling is well under half of the old monolithic `ci.yml`
ceiling, and the common case (a single-service change) is closer to a fifth.
The heavy jobs (postgres integration, research double-run repro, dashboard
build via `test-deploy`) move to `ci-full.yml`, which by default **does not
run at all** on a PR unless it carries the `full-ci` label — see
`docs/ci/ACTIONS_OPTIMIZATION_STAGE_2.md`.

## Structural inventory: Stage 2 full lane (`ci-full.yml`)

Unchanged in scope from the old `ci.yml` heavy jobs — same jobs, same
commands, just gated behind `should-run` (push to `main`, `workflow_dispatch`,
`merge_group`, or a labeled PR) instead of running on every PR push.

| Job | `timeout-minutes` (ceiling) |
|---|---|
| `full-quality` | 15 |
| `core-tests` | 30 |
| `postgres-and-reporting` | 30 |
| `research-repro` | 20 |
| **Total ceiling** | **95 minutes/run**, but only when `should-run` says yes |

## Bottom line

The savings claim Stage 2 makes is structural, not measured: **most PR
pushes now skip ~95 minutes of ceiling entirely** (the full lane), and the
fast lane itself skips job slices that are provably unrelated to the diff.
Confirm the real number with the `gh api .../timing` commands above once
Stage 2 has real traffic.
