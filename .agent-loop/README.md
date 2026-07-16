# Codex review gate (`.agent-loop`)

Read-only Codex review gate for feature branches. Produces a schema-validated JSON verdict from the real git diff versus a stable base ref. Does **not** auto-merge.

## Prerequisites

- **git** on `PATH`
- **Python 3.11+** on `PATH`
- **jsonschema** (`pip install jsonschema`) for `validate-review-result.py`
- **PowerShell**: prefer **`pwsh`** (PowerShell 7+) on PATH for CI/Linux; Windows may fall back to `powershell`
- **Codex CLI** (optional for local mock/tests): must be installed and authenticated for live reviews

### Check Codex CLI

```powershell
codex --version
```

If the CLI is missing and you do not pass `-MockResultPath`, the gate writes a `REVIEW_FAILED` result and exits `3`.

## How to run

From the repo root (or any subdirectory — the script resolves the git toplevel). Prefer `pwsh` when available:

```powershell
pwsh -ExecutionPolicy Bypass -File .agent-loop/run-codex-review.ps1 -BaseRef origin/main
```

### Note for issue #141

For PR/issue **#141** and similar feature work branching from main, set **`-BaseRef origin/main`** (stable tip). Do not use a moving feature-branch tip as the review base.

### Companion alias

`run-review-loop.ps1` is a thin wrapper that forwards all arguments to `run-codex-review.ps1` (compatibility with prior docs / issue #149):

```powershell
powershell -ExecutionPolicy Bypass -File .agent-loop/run-review-loop.ps1 -BaseRef origin/main
```

## Exit codes

| Code | Meaning |
|------|---------|
| **0** | `APPROVED` |
| **2** | `CHANGES_REQUIRED` |
| **3** | `REVIEW_FAILED` (empty diff, secrets in diff, missing Codex, invalid/unusable result, git state failure) |
| **4** | Stale/wrong review (`reviewed_head` / `reviewed_base` / `reviewed_diff_hash` mismatch) |

## Result JSON (schema 1.0)

Written to `.agent-loop/codex-review-result.json`. Fields:

| Field | Description |
|-------|-------------|
| `schema_version` | Const `"1.0"` |
| `verdict` | `APPROVED` \| `CHANGES_REQUIRED` \| `REVIEW_FAILED` |
| `reviewed_base` | Full merge-base SHA used for the diff |
| `reviewed_head` | Full HEAD (or `-HeadRef`) SHA |
| `reviewed_diff_hash` | SHA256 of canonical UTF-8 (no BOM) diff bytes |
| `summary` | Short overall assessment |
| `findings` | Array of structured findings (see schema) |
| `required_tests` | Suggested / required tests |
| `review_notes` | Non-finding notes |

Verdict rules (enforced by `validate-review-result.py`):

- `APPROVED` must not contain `BLOCKER`/`MAJOR`
- `CHANGES_REQUIRED` requires at least one `BLOCKER`/`MAJOR`
- `REVIEW_FAILED` allows empty or any findings

## `review-history/`

Each successful validation path also copies an immutable snapshot to:

`.agent-loop/review-history/<UTC yyyyMMddTHHmmssfffZ>_<SHORT_SHA>.json`

If that name already exists, a numeric suffix (`_1`, `_2`, …) is appended — existing files are never overwritten.

Use this for audit trails across Cursor rounds. Do not edit history files in place.

## Cursor loop policy

- Maximum **3** Cursor agent rounds per review cycle for addressing Codex findings.
- After 3 rounds without `APPROVED`, stop and escalate (human decision / split the PR).

## Handling false findings

If Codex reports a false positive:

1. Document why in `review_notes` on a follow-up review, or in the PR.
2. Prefer a targeted code comment / test that proves safety over arguing in chat only.
3. Do not loosen production assertions solely to clear a finding.

## What `REVIEW_FAILED` means

The gate could not produce a trustworthy approve/changes verdict. Common causes:

- Empty diff versus merge-base (nothing to review)
- Secret-like patterns in the diff (Codex is **not** invoked)
- Codex CLI unavailable without a mock
- Result JSON missing, unparseable, or failing schema/verdict rules (non-stale)

Fix the underlying problem and re-run. Exit code `3`.

## No auto-merge

An `APPROVED` verdict is a **gate signal only**. It does not merge, push, deploy, or bypass human review requirements.

## Applying to feature branches

1. Checkout your feature branch.
2. Ensure `origin/main` is fetched.
3. Run with `-BaseRef origin/main`.
4. Address `CHANGES_REQUIRED` findings, commit, re-run.
5. Attach or link `codex-review-result.json` / history entry in the PR as needed.

## Security model

- **Secret scan** runs on the diff before Codex (`secret_scan.py`). Matches abort with `REVIEW_FAILED` and never send the patch to Codex.
- CLI stderr reports **pattern name + line number only** — never secret values or line previews.
- Patterns cover common DB URLs (including SQLAlchemy `postgresql+psycopg://…`), `RAILWAY_TOKEN` / `SESSION_SECRET` / credentialed `DATABASE_URL` assignments, plus API keys and tokens.
- Do not place secrets, `.env`, or status dumps (e.g. `.codex/railway-status-*.json`) into the review inputs.
- Live Codex is invoked with explicit read-only automation flags: `--sandbox read-only`, `--ask-for-approval never`, `--ignore-user-config` (plus `--ignore-rules` / `--ephemeral` when the CLI supports them). Missing sandbox flags → `REVIEW_FAILED`.
- After Codex returns, the gate **rechecks HEAD** (and diff hash) before accepting `APPROVED`; drift → exit `4`.
- Override for tests: `AGENT_LOOP_CODEX_BIN` / `-CodexBin`, and `AGENT_LOOP_POST_CODEX_HEAD` to force a post-Codex stale HEAD.
- Diff and ephemeral inputs under `.agent-loop/tmp/` and `current-review-input.txt` should stay gitignored.

## Mock mode (tests)

For unit/integration tests without calling Codex:

```powershell
powershell -ExecutionPolicy Bypass -File .agent-loop/run-codex-review.ps1 `
  -BaseRef origin/main `
  -SkipCodex `
  -MockResultPath tests/agent_loop/fixtures/approved.json
```

- `-MockResultPath` ? use a fixture JSON as the Codex output (implies skip live Codex).
- `-SkipCodex` ? do not invoke Codex; requires `-MockResultPath` for a usable result path.
- By default, when a mock is used, `reviewed_base` / `reviewed_head` / `reviewed_diff_hash` are overlaid with the actual run values (placeholders like `WILL_BE_SET`, or when `AGENT_LOOP_OVERLAY_REFS=1`). Use `-PreserveMockRefs` for stale-head / wrong-hash tests.
- `-DiffFile` ? supply a precomputed patch instead of `git diff` (tests).
- `-AllowEmptyDiff` ? tests only; default is to fail empty diffs.

## Scripts reference

| Path | Role |
|------|------|
| `run-codex-review.ps1` | Main gate orchestration |
| `run-review-loop.ps1` | Alias wrapper |
| `codex-review-prompt.md` | Codex instructions |
| `codex-review-schema.json` | JSON Schema draft-07 |
| `secret_scan.py` | Pre-Codex secret patterns |
| `validate-review-result.py` | Schema + verdict + expected refs |
