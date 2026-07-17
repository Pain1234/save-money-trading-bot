# Public-release security audit (retrospective)

Issue: **#177**. Parent epic: **#176**.

**Audit date (UTC):** 2026-07-17  
**Scope note:** This repository is **already public**. This document is a **retrospective** readiness audit for formal public-release acceptance, not a visibility flip.

**Rule:** This report intentionally contains **no secret values**.

## Method

1. Current tree scan for high-risk patterns (AWS key prefix, PEM headers, GitHub PAT prefix, Slack token prefix, secret-like assignments).
2. Tracked env/credential filenames (.env*, *credential*, *.pem).
3. Git history pickaxe (git log -S) for the same high-risk prefixes across --all.
4. Review of .gitignore secret ignore rules.
5. Spot-check of known secret-handling code (dashboard auth env readers, paper trading URL docs).
6. Issues/PRs/Actions: process review — full manual reading of every historical comment/log is not claimed; high-risk patterns above cover code history. Actions log retention is time-limited on GitHub.

## Current tree

| Check | Result |
|-------|--------|
| Real .env tracked | No (ignored; only .env.example) |
| PEM / wallet private keys in tree | None found |
| Live API tokens in source | None found |
| src/lib/auth/credentials.ts | Reads AUTH_USERNAME / AUTH_PASSWORD_HASH from **environment** only |
| .env.example | Placeholders / commented local test URL pattern only |

Heuristic assignment matches (docs/tests/scripts) were inspected and classified as **non-secret** placeholders or intentional scanner fixtures.

## History

Pickaxe hits for ghp_, AKIA, PEM headers, xoxb- resolve to **historical secret-scanner fixtures / pattern definitions** from retired tooling commits (formerly under tests/agent_loop and .agent-loop), not production credentials.

No tracked commit added a live .env (only .env.example).

## Issues / PRs / Actions

- Do not paste secrets into issues/PR bodies (reinforced by CONTRIBUTING / governance docs).
- Actions artifacts: treat as potentially sensitive operational output; do not upload private research results. Full historical Actions log review is **limited by GitHub retention**; no evidence of intentional secret upload workflows in .github/workflows/.

## Findings

| ID | Severity | Finding | Disposition |
|----|----------|---------|-------------|
| F1 | Info | Repo was made public before this formal audit | Accepted: audit is retrospective; checklist still required for formal acceptance |
| F2 | Info | Synthetic secret **fragments** exist in tests for scanner coverage | Keep; do not treat as credentials; never replace with real values |
| F3 | Low | Example DB URL comments use password placeholder tokens | Acceptable; ensure real passwords stay out of git |
| F4 | Process | History rewrite not indicated | No rewrite; separate human decision required if a real secret is ever found later |

**Exposed credentials requiring rotation:** none identified in this audit.

## Remediations applied in this PR

- Publish this audit record under docs/governance/.
- Cross-link from [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md).

## Residual risk / owner actions

- Rotate any credential that ever touched a local .env if that file was shared outside the machine.
- If a future finding appears in history, **do not** consider deleting the tip file sufficient; open a dedicated incident issue (possible history rewrite only with explicit human approval).
- Formal public-release still requires completing [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) with a human approval comment on #176/#177.

## Sign-off

Auditor: agent executing P4 rest-close plan.  
Owner approval for accepting this retrospective audit: plan execution request + merge of the closing PR for #177.
