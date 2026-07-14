# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `docs/operations/metrics.md` - critical operational metrics catalog (Issue #16).
- `docs/operations/idempotency-audit.md` - idempotency path inventory (Issue #13).
- `docs/runbooks/worker-restart.md` - worker restart runbook (Issue #14).

### Changed

- GitHub default branch migrated from `cursor/railway-paper-dashboard-v1` to `main`
  (Issue #64, commit `10000d3`). Rollback branch retained.
- Branch protection with required CI checks enabled on `main` (Issue #65).
- `.github/workflows/ci.yml` — CI push trigger includes `main`.
- `docs/default-branch-migration-plan.md`, `docs/branch-protection.md` — post-migration
  status.

## [baseline-paper-v1.0.1] — 2026-07-14

Post-tag baseline after `baseline-paper-v1.0.0` (merge of PR #63). Documentation and
lock-file fixes only — `baseline-paper-v1.0.0` (`daacb627`) is unchanged.

### Added

- `requirements-baseline.txt` — portable pinned Python transitive PyPI dependencies (Issue #8); regenerated on Python 3.12.
- `scripts/export_requirements_baseline.py` — regenerate lock file from clean venv; strips local project refs; Python 3.12 export enforcement.
- CI job `requirements-baseline` — `pip install -r requirements-baseline.txt` on Python 3.12 / ubuntu-latest.
- CI jobs `test-market-data` and `test-deploy` in `.github/workflows/ci.yml`.

### Changed

- `docs/baseline-paper-v1.md` — dashboard env vars documented; honest CI vs full-suite test counts.
- `README.md` — dashboard local dev requires `PRIVATE_PAPER_API_URL` for server routes; Railway uses `node server.js` standalone.
- `ROADMAP.md` — P1 tag released; post-tag follow-ups documented separately.
- `.github/workflows/ci.yml` — unit job includes `paper_trading` and `market_data` (excludes `postgres`, `live`, `soak`).

### Fixed

- Issue #58 — dashboard build test failure traced to missing `npm ci` (not source defect); documentation corrected (not mock-by-default for `/dashboard`).

## [baseline-paper-v1.0.0] — 2026-07-14

Tagged at commit `daacb627` (merge of PR #62). P1 reproducible paper-trading baseline.

### Added

- `.github/workflows/ci.yml` — CI gate (validate, lint, unit test, PostgreSQL integration).
- `docs/default-branch-migration-plan.md` — plan for `main` default branch (#52; migration not executed).

### Changed

- `docs/baseline-paper-v1.md` — P1 reproducible baseline reference (start paths, versions, test inventory).
- `README.md` — aligned with PostgreSQL/Railway architecture.

### Notes

- Branch protection and mandatory required checks remain pending human approval (#52 execution issue).
- Full 782-test suite is not entirely CI-gated; see `docs/baseline-paper-v1.md` for counts.

## [Unreleased — prior entries]

### Changed

- `ROADMAP.md` — P0 marked complete with documented deviations (#52, ADR-011).
- `docs/DEFINITION_OF_DONE.md` — Issue #5 closed; test-evidence baseline PRs (#50, #54, #57); DoD section demonstrated in #57.
- `docs/DECISION_LOG.md` — ADR-011 solo-maintainer DoD enforcement.
- `docs/ARCHITECTURE.md` — CI section corrected: governance workflow present; full pytest CI gap (#53) documented (Issue #3).
- `docs/DEFINITION_OF_DONE.md` — removed incorrect post-governance baseline PR table; enforcement per ADR-011.

### Added

- `docs/baseline-paper-v1.md` — P1 reproducible baseline (start paths, runtime versions, test inventory, tag criteria).
- `docs/ARCHITECTURE.md` — evidence-based system architecture map.
- `docs/PROJECT_OPERATING_SYSTEM.md` — GitHub-centric workflow, bugfix process, WIP limits, GitHub Project manual steps.
- `docs/DEFINITION_OF_DONE.md` — general, research, and bugfix checklists.
- `docs/DECISION_LOG.md` — ADR-style decision register (evidence-based entries).
- `docs/RISK_REGISTER.md` — initial risk catalog with status (open/planned/partial).
- `docs/EXPERIMENT_TEMPLATE.md`, `docs/STRATEGY_LIFECYCLE.md`, `docs/strategies/README.md`.
- `docs/incidents/` and `docs/runbooks/` template structures.
- `.cursor/rules/project-governance.mdc` — persistent Cursor agent rules.
- `.github/ISSUE_TEMPLATE/` — bug, roadmap task, research experiment, incident forms.
- `.github/PULL_REQUEST_TEMPLATE.md`.
- `scripts/github_project_setup.py` — GitHub labels, milestones, and seed issues (`--dry-run` / `--apply`); stable seed keys and sequential idempotency tests (Issue #51).
- `.github/workflows/github-governance-setup.yml` — PR validation and manual governance apply with concurrency serialization; official apply uses `--skip-project`.
- `tests/governance/test_github_project_setup.py` — governance setup unit tests including repository fail-closed repair guards.

### Changed

- `docs/ARCHITECTURE.md` — verified production entrypoints table; migrations `001`–`009`; `trading_constraints` module (Issue #3).
- `docs/DEFINITION_OF_DONE.md` — binding review policy (ADR-010); enforcement evidence tracked in Issue #5.
- `docs/RISK_REGISTER.md` — top-5 risks linked to GitHub issues #45–#49 (Issue #6).
- `scripts/github_project_setup.py` — stable seed keys, refresh-before-create, duplicate repair mode, repository fail-closed guards, and sequential idempotency tests (Issue #51).
- Governance docs — idempotency claims corrected; official Actions apply uses `--skip-project`; duplicate repair restricted to approved repository with identity verification.
- `README.md` — aligned with PostgreSQL/Railway architecture; links P1 baseline doc.
- `ROADMAP.md` — P1 in progress; P0 exit remains open (see PR #57).
- `services/paper_trading/README.md` — migration range corrected to `001`–`009`.

### Security

- No credential or permission changes.
