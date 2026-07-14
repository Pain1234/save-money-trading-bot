# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `requirements-baseline.txt` — pinned Python transitive dependencies for P1 baseline (Issue #8).
- `scripts/export_requirements_baseline.py` — regenerate lock file from clean venv.

### Changed

- `docs/baseline-paper-v1.md` — dashboard local vs production guidance; honest test inventory; tag gate remains **open**; PostgreSQL local blocker documented; Issue #58 resolution.
- `README.md` — dashboard requires `npm ci`; separate local dev vs production build paths.
- `ROADMAP.md` — P0 attribution corrected (not PR #55); P1 tag gate open.
- Removed premature `[baseline-paper-v1.0.0]` changelog section — tag not created; gate open (Issue #10).

### Fixed

- Issue #58 — dashboard build test failure traced to missing `npm ci` (not source defect).

### Planned — `baseline-paper-v1.0.0` (Issue #10, tag not created)

Criteria and notes for the future tag release (do not tag until checklist in
`docs/baseline-paper-v1.md` is complete):

- `.github/workflows/ci.yml` — mandatory CI gate (validate, lint, unit test, PostgreSQL integration).
- `docs/default-branch-migration-plan.md` — plan for `main` default branch (#52; migration not executed).
- Remaining gaps before tag: documented PostgreSQL run evidence, Python lock on 3.12, branch protection (#52).

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
