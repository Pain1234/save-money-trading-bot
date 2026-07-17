# Codex review gate (`.agent-loop`)

Read-only Codex review gate for feature branches. Produces a schema-validated JSON verdict from the real git diff versus a stable base ref. Does **not** auto-merge.

## Prerequisites

- **git** on `PATH`
- **Python 3.11+** on `PATH`
- **jsonschema** (`pip install jsonschema`) for `validate-review-result.py`
- **PowerShell**: prefer **`pwsh`** (PowerShell 7+) on PATH for CI/Linux; Windows may fall back to `powershell` for mock/DiffFile tests. **Live Codex reviews require PowerShell 7+** (`Process.Kill($true)` process-tree support).
- **Codex CLI** (optional for local mock/tests): must be installed and authenticated for live reviews
- Child Codex temp dirs use `[System.IO.Path]::GetTempPath()` (Python: `tempfile.gettempdir()`); parent `TEMP`/`TMP`/`TMPDIR` may be absent (e.g. Linux CI) without failing the gate.

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
| **3** | `REVIEW_FAILED` (empty diff, secrets in diff, missing Codex, Codex process error, invalid/unusable result, git state failure) |
| **4** | Stale/wrong review (`reviewed_head` / `reviewed_base` / `reviewed_diff_hash` mismatch) |

### BaseRef resolution

`-BaseRef` defaults to `origin/main`. The gate resolves refs in order: explicit `-BaseRef`, then `origin/main`, `main`, `master`. If none resolve and you did **not** pass `-DiffFile`, the gate fails with a clear error (common on shallow GitHub Actions checkouts that lack `origin/main`).

**DiffFile offline mode:** when `-DiffFile` is set and BaseRef (or merge-base) cannot be resolved, the gate sets `reviewed_base = reviewed_head`, skips the merge-base requirement, and continues with the provided patch.

**DiffFile is gated (mock/test only):** `-DiffFile` is accepted only when **both** `AGENT_LOOP_TEST_MODE=1` **and** a non-empty `-MockResultPath` are set. `AGENT_LOOP_ALLOW_DIFF_FILE` alone is **not** sufficient. DiffFile never starts a live Codex process. Production reviews always build `git diff --binary <merge-base>..<reviewed-head>`.

Pytest `run_gate()` sets `AGENT_LOOP_TEST_MODE=1` automatically when DiffFile is used; tests must still pass `-MockResultPath`.

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
- Codex process exited non-zero (gate exit `3`, verdict `REVIEW_FAILED`)
- Result JSON missing, unparseable, or failing schema/verdict rules (non-stale)
- BaseRef unresolved without `-DiffFile` (shallow clone / missing `origin/main`)

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
- For unified diffs, only **added** lines (`+`, excluding `+++` headers) are scanned — deletion hunks do not abort (so removing legacy fixtures is safe), while newly introduced secret-like text still fails closed.
- CLI stderr reports **pattern name + line number only** — never secret values or line previews.
- Patterns cover common DB URLs (including SQLAlchemy `postgresql+psycopg://…`), `RAILWAY_TOKEN` / `SESSION_SECRET` / credentialed `DATABASE_URL` assignments, plus API keys and tokens.
- Do not place secrets, `.env`, or status dumps (e.g. `.codex/railway-status-*.json`) into the review inputs.
- **Allowlist review workspace (fail-closed):** live Codex runs in a **temp directory outside the repo** built by `build_review_workspace.py --git-rev <reviewed_head>`. Diff paths are materialized from **git blobs** (`git show <rev>:<path>`), never copied from the worktree. Symlinks (`120000`) are rejected. If any deny-listed path appears in the diff (`.env`, `.codex/**`, `auth.json`, `*secret*`, credentials, private keys / `id_ed25519` / `*.pem` / `*.keystore`, etc.), the builder exits `1` and the gate returns `REVIEW_FAILED` — no usable workspace. Prompt, schema, patch, and optional `AGENTS.md` are still copied as review artifacts. Manifest lists allowlisted / skipped_missing / git_rev / out_dir_name only (no absolute `repo_root`).
- **OS isolation:** on Linux/Unix the gate `chmod 000`s the repo root during Codex (then restores). Skipping isolation requires **both** `AGENT_LOOP_SKIP_OS_ISOLATION=1` **and** `AGENT_LOOP_TEST_MODE=1` (test/mocks only). `SKIP_OS_ISOLATION` alone → `REVIEW_FAILED` exit `3`. Other platforms without that pair → `REVIEW_FAILED`.
- **Auth isolation:** Live Codex gets an ephemeral `CODEX_HOME` **outside** the review workspace. For Codex CLI 0.144+ ChatGPT login, the gate copies `~/.codex/auth.json` into that temp home (required: `id_token` + `access_token`). Env-only `CODEX_ACCESS_TOKEN` is not sufficient on 0.144+. API-key mode may still use scrubbed `CODEX_API_KEY` in the child env. **Never** set `OPENAI_API_KEY` on the Codex child. Temp extract files are deleted immediately. After the run, `auth.json` is always deleted (`AGENT_LOOP_KEEP_AUTH=1` may keep only the home + marker, never `auth.json`). Missing auth → `REVIEW_FAILED`.
- **Scrubbed child environment:** `Invoke-CodexCommand` launches Codex via `ProcessStartInfo` with an allowlisted env (PATH / temp / locale / `CODEX_HOME` / `CODEX_*` credentials / selected `AGENT_LOOP_*` mock side-channels). Parent secrets such as `DATABASE_URL`, `PASSWORD`, `OPENAI_API_KEY`, `RAILWAY_*`, `SESSION_SECRET`, and other `*SECRET*` / `*TOKEN*` values are **not** inherited.
- **Stdout / stderr hygiene:** Codex stdout and stderr are captured separately. When the CLI advertises `--output-last-message`, the gate uses that file for the verdict JSON; otherwise JSON is parsed from **stdout only** (never stderr). Temp `codex-stdout-*` / `codex-stderr-*` / last-message files are deleted afterward unless `AGENT_LOOP_KEEP_CODEX_OUTPUT=1`.
- Live Codex is invoked with explicit read-only automation flags: `--sandbox read-only`,
  `--ignore-user-config` (plus `--ask-for-approval never` when the CLI still advertises it,
  `--ignore-rules` / `--ephemeral` / `--output-last-message` when supported). Missing required
  sandbox flags → `REVIEW_FAILED`.
- **Windows:** `chmod` OS isolation is unavailable. Live reviews still run using the allowlisted
  temp workspace + Codex `--sandbox read-only` + scrubbed child env (no `uname` probe crash).
- After Codex returns, the gate **rechecks HEAD** (and diff hash) before accepting `APPROVED`; drift → exit `4`.
- Override for tests: `AGENT_LOOP_CODEX_BIN` / `-CodexBin`, `AGENT_LOOP_TEST_MODE=1` + `AGENT_LOOP_SKIP_OS_ISOLATION=1`, `AGENT_LOOP_ALLOW_DIFF_FILE=1` for `-DiffFile`, and `AGENT_LOOP_POST_CODEX_HEAD` to force a post-Codex stale HEAD.
- Diff and ephemeral inputs under `.agent-loop/tmp/` and `current-review-input.txt` should stay gitignored.

## BOOTSTRAP EXCEPTION

Das Codex-Review-Gate kann vor seinem ersten Merge nicht verbindlich seine
eigene Freigabe erzeugen.

Für genau diesen initialen Tooling-PR gilt daher einmalig:

- vollständiges grünes CI
- menschliches Review
- keine offenen BLOCKER oder MAJOR Findings
- keine Änderungen an Trading-Code
- kein automatischer Merge
- kein Deployment

Nach dem Merge ist das Gate für alle nachfolgenden Feature-PRs verbindlich,
beginnend mit Issue #141.

Diese Ausnahme gilt nicht für spätere Änderungen am Gate.
Spätere Gate-Änderungen benötigen entweder:

- das bereits gemergte Gate der vorherigen Version
- oder ein separates menschlich freigegebenes Notfallverfahren

## Mock mode (tests)

For unit/integration tests without calling Codex:

```powershell
powershell -ExecutionPolicy Bypass -File .agent-loop/run-codex-review.ps1 `
  -BaseRef origin/main `
  -SkipCodex `
  -MockResultPath tests/agent_loop/fixtures/approved.json
```

- `-MockResultPath` — use a fixture JSON as the Codex output (implies skip live Codex).
- `-SkipCodex` — do not invoke Codex; requires `-MockResultPath` for a usable result path.
- By default, when a mock is used, `reviewed_base` / `reviewed_head` / `reviewed_diff_hash` are overlaid with the actual run values (placeholders like `WILL_BE_SET`, or when `AGENT_LOOP_OVERLAY_REFS=1`). Use `-PreserveMockRefs` for stale-head / wrong-hash tests.
- `-DiffFile` — supply a precomputed patch instead of `git diff` (tests / offline). Requires `AGENT_LOOP_ALLOW_DIFF_FILE=1`. If BaseRef cannot be resolved, uses reviewed_base=reviewed_head.
- `-AllowEmptyDiff` — tests only; default is to fail empty diffs.

## Scripts reference

| Path | Role |
|------|------|
| `run-codex-review.ps1` | Main gate orchestration |
| `run-review-loop.ps1` | Alias wrapper |
| `build_review_workspace.py` | Allowlisted Codex workspace (secret isolation) |
| `extract_codex_auth_env.py` | Map auth.json → `CODEX_ACCESS_TOKEN` / `CODEX_API_KEY` (never `OPENAI_API_KEY`) |
| `codex-review-prompt.md` | Codex instructions |
| `codex-review-schema.json` | JSON Schema draft-07 |
| `secret_scan.py` | Pre-Codex secret patterns |
| `validate-review-result.py` | Schema + verdict + expected refs |

<!-- ci-trigger -->
