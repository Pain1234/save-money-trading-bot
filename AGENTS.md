# Agent Operating Rules

Binding rules for Cursor, Codex, and other coding agents working in this repository.

**Project goal:** Build a system that filters bad strategies, credibly validates good ones, measures execution deviation, and never risks more capital than proven maturity justifies — not a perfect trading bot.

**Source of truth:** GitHub (issues, milestones, pull requests, `docs/DECISION_LOG.md`). Chat is the workbench; GitHub is the project memory.

---

## Project status

This repository contains a paper-trading and research system. Live trading,
wallet signing and automatic deployment are outside the current scope
unless a separately approved milestone (see §12, `human-approval-required`)
explicitly authorizes them.

## Agent roles

- Cursor is the implementation agent: writes code, tests, docs, and commits.
- Codex is the independent, read-only reviewer: Codex must not edit files,
  commit, push, merge, or deploy.
- Humans approve merges, releases, and deployments.

## Mandatory quality gate

Every feature change must follow this 9-step gate, enforced in detail by
`.cursor/rules/00-mandatory-codex-review.mdc`:

1. Implement on a feature branch (never directly on `main`).
2. Add or update tests.
3. Run relevant tests and static checks (lint, `git diff --check`).
4. Commit the reviewed state.
5. Run `.agent-loop/run-codex-review.ps1` against the actual PR base.
6. Address confirmed BLOCKER and MAJOR findings only — do not apply Codex
   suggestions unchecked.
7. Repeat steps 5–6 for at most three review rounds.
8. Require Codex `APPROVED` on the current HEAD before calling the change
   merge-ready ("fertig").
9. Never merge or deploy automatically — a human makes that call.

A missing, failed, or stale Codex review is not approval.

## Safety constraints

Never:

- expose credentials or private data
- enable live trading
- add wallet signing without an approved P8 issue and human sign-off
- weaken risk limits outside an explicitly approved issue
- disable tests to obtain a passing result
- overwrite unrelated local modifications
- work directly on `main`
- auto-merge or auto-deploy

## Source of detailed Cursor workflow

The step-by-step Cursor execution rules — pre-work checks, the Codex gate
command, prohibited actions, and the approval rule — are stored in:

`.cursor/rules/00-mandatory-codex-review.mdc`

---

## 1. Before every task

Read, in order:

1. This file (`AGENTS.md`)
2. `ROADMAP.md` (active phase and gates)
3. The **linked GitHub issue** for the current branch/PR
4. Relevant docs:
   - `docs/ARCHITECTURE.md`
   - `docs/PROJECT_OPERATING_SYSTEM.md`
   - `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md` (public core vs private edge)
   - `docs/strategy-specification.md`, `docs/risk-specification.md` (when touching strategy/risk)
   - `docs/paper-trading-orchestrator-v1.md` (when touching paper trading)
   - Area-specific READMEs under `services/*/`

Do not start implementation without a clear issue scope.

---

## 2. One issue per branch and PR

- One clearly defined GitHub issue per branch and pull request.
- Branch names should reference the issue when possible (e.g. `fix/123-heartbeat-stale`).
- Do not bundle unrelated fixes.

---

## 3. No scope expansion without a new issue

- New problems discovered during work → **new issue**, not silent scope creep.
- Refactors, dependency upgrades, and doc rewrites outside the issue → separate issue unless trivial (typo).

---

## 4. Do not silently change

Without an explicit issue **and** human approval where noted:

| Area | Examples |
|------|----------|
| Strategy parameters | Entries in `docs/strategy-specification.md`, engine config |
| Fee / slippage assumptions | Backtest and paper fill models |
| Risk limits | `docs/risk-specification.md`, kill switch behavior |
| Production start commands | `deploy/scripts/*.sh`, Railway TOML start commands |
| Database schema | Alembic migrations |
| Live trading | Wallet, signing, real exchange orders |

**Paper trading V1:** Real Hyperliquid private API, wallet signing, and live orders are **not implemented** — do not enable.

---

## 5. Bugfixes: no drive-by refactors

During a bugfix, do not perform unrelated refactors. Minimal diff only.

---

## 6. Bugfix quality bar

Every important bug should have, when feasible:

1. Reproducible failure (steps or test)
2. Regression test
3. Documented root cause (issue or PR)
4. Minimal fix
5. Assessment of downstream impact (PnL, positions, research results)

Severity guide: see `docs/PROJECT_OPERATING_SYSTEM.md` (S1–S4).

---

## 7. Research results must include

- Experiment-ID
- Git commit hash
- Dataset version / manifest ID
- Full configuration (frozen)
- Cost assumptions
- Result summary
- **Accept** or **reject** with rationale

Use `docs/EXPERIMENT_TEMPLATE.md`.

---

## 8. Do not overwrite historical research

- Append new experiments; do not delete prior results.
- Invalid results: mark `status:invalidated` (label/issue) and document why; do not silently replace.

---

## 9. Update tests and docs with code

- Behavior change → tests + doc update in the same PR when reasonable.
- Governance-only changes → update relevant governance docs.

---

## 10. Never fabricate test results

- Run commands; report actual pass/fail.
- If tests cannot run (missing DB, gh auth), state that explicitly.

---

## 11. Incidents for critical execution/accounting failures

S1 issues (wrong orders/positions, capital risk, state corruption, security) require incident documentation using `docs/incidents/INCIDENT_TEMPLATE.md` after stabilization.

---

## 12. Human approval required

These require a dedicated issue labeled `human-approval-required` and explicit human sign-off before merge/deploy:

- Live trading or micro-live activation
- New exchange integration
- Leverage increases
- Capital limit increases
- Production credential or permission changes
- Roadmap phases **P8** and **P9**

---

## 13. Handover template

At the end of every task, provide:

```text
Umgesetzt:
Geänderte Dateien:
Ausgeführte Tests:
Offene Punkte:
Risiken:
Nächster sinnvoller Schritt:
```

Link the GitHub issue and PR. Do not rely on chat-only documentation for decisions — update `docs/DECISION_LOG.md` or the issue.

---

## Quick references

| Task | Command / path |
|------|----------------|
| Tests (paper, postgres) | `python -m pytest tests/paper_trading -m postgres -v` |
| Full tests | `python -m pytest tests/ -v` |
| Lint | `ruff check .` |
| Types | `mypy .` (if configured) |
| Migrations | `python -m alembic upgrade head` |
| Worker start (prod path) | `deploy/scripts/start-worker.sh` |
| Governance setup (dry) | `python scripts/github_project_setup.py --dry-run` |

See `README.md` and service READMEs for environment variables. Never commit secrets.
