# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- `ROADMAP.md` — P0 marked complete with documented deviations (#52, ADR-011).
- `docs/DEFINITION_OF_DONE.md` — Issue #5 closed; baseline PR evidence (#50, #54, #57).
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
