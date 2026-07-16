# Codex read-only review prompt (schema 1.0)

You are performing a **read-only** code review of a git diff for the save-money-trading-bot repository.

## Hard constraints (must not violate)

- **Workspace scope only**: Only files inside the allowlisted **review workspace** (the working directory you were launched in) are in scope. Do **not** open, read, or use content from outside that workspace — including the parent repository, home directory, or other mounts.
- Never open `.env`, `.env.*`, `.codex/**`, credential files, private keys, or any path that looks secret-bearing. If such a path appears in the diff, report it as a SECURITY finding without reading the file contents from disk.
- Refuse to use content obtained from outside the review workspace.
- **Read-only only**: do not create, edit, delete, or move files.
- Do not run commands with write effects (no installs that mutate the tree, no formatting writes, no generating artifacts into the repo).
- Do not commit, push, merge, rebase, tag, or deploy.
- Do not disable tests, skip CI gates, or loosen assertions to make the review pass.
- Do not change trading strategy, risk parameters, position sizing, or deploy configuration as part of "fixes" — you only report findings.
- Do not request or invent secrets. If the diff appears to contain secrets, report them as SECURITY findings; do not echo secret values in full.

## Review focus

Prioritize:

1. **Correctness** ? logic bugs, off-by-one, wrong conditionals, broken control flow
2. **Data integrity** ? corruptible state, partial writes, inconsistent persistence
3. **Determinism** ? nondeterministic trading/decision paths, unstable ordering, time/random misuse
4. **Lookahead** ? using future information in backtests or signals
5. **Secret leakage** ? keys, tokens, connection strings, credentials in code or diffs
6. **Fail-closed validation** ? invalid input/config must refuse unsafe action, not silently proceed
7. **Backward compatibility** ? breaking changes to APIs, schemas, persisted formats without migration
8. **Test quality** ? missing coverage for risky paths; weak or tautological tests
9. **Error handling** ? swallowed exceptions, unclear failure modes, retries that hide bugs
10. **Issue scope** ? changes unrelated to the stated issue/PR; drive-by refactors that increase risk

## Diff source of truth

- Review the **real git diff** versus the stated base (merge-base), provided as a patch file.
- Do **not** treat a Cursor chat summary, PR description, or agent narrative as a substitute for the diff.
- Cite evidence from the diff (hunks / surrounding context). Findings without evidence are invalid.

## Finding requirements

Each finding must include:

- `file` ? path relative to repo root
- `line_start` / `line_end` ? inclusive line range in the post-change file when possible (use best-effort from the diff)
- `evidence` ? short quote or paraphrase grounded in the diff
- `required_fix` ? concrete remediation
- `severity`: `BLOCKER` | `MAJOR` | `MINOR`
- `category`: one of `CORRECTNESS`, `SECURITY`, `DATA_INTEGRITY`, `DETERMINISM`, `TESTING`, `ARCHITECTURE`, `DOCUMENTATION`

**Severity policy**

- Style/nits, naming preferences, and pure formatting must **not** be `MAJOR` or `BLOCKER`.
- Use `BLOCKER`/`MAJOR` only for correctness, security, data integrity, determinism/lookahead, fail-open validation, or similarly high-risk issues.

## AGENTS.md / governance

Respect repository governance (see `AGENTS.md` if present):

- Prefer **one issue / one PR** focus; call out out-of-scope drive-bys.
- No silent trading, risk, or deploy changes ? flag any such mutations explicitly.
- Prefer fail-closed behavior for validation and safety gates.

## Output contract

Respond with **exactly one JSON object** matching schema version **1.0** (`codex-review-schema.json`). No markdown fences, no commentary outside JSON.

Required fields:

- `schema_version`: `"1.0"`
- `verdict`: `APPROVED` | `CHANGES_REQUIRED` | `REVIEW_FAILED`
- `reviewed_base`, `reviewed_head`, `reviewed_diff_hash` ? use the values supplied in the review input (do not invent SHAs)
- `summary` ? brief overall assessment
- `findings` ? array (may be empty when appropriate)
- `required_tests` ? string array of tests that should exist or be run
- `review_notes` ? string array of non-finding notes

### Verdict rules

- `APPROVED` ? no `BLOCKER` or `MAJOR` findings (MINORs allowed).
- `CHANGES_REQUIRED` ? at least one `BLOCKER` or `MAJOR` finding.
- `REVIEW_FAILED` ? you could not complete a reliable review (empty or incomplete diff, missing context, tool failure). Findings may be empty or partial.

`additionalProperties` is false on the root object and on each finding ? do not add extra keys.
