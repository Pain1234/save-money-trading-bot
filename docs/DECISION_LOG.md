# Decision Log

Architecture and governance decisions in ADR style. Only **Accepted** entries below are evidenced by the current repository; others are placeholders for future decisions.

---

## ADR-001 – Strategy V1 specification as frozen reference

**Status:** Accepted  
**Date:** Documented in repository (see `docs/strategy-specification.md` revision history)

**Context:** Trend Strategy V1 requires a single authoritative spec before research validation and paper trading parity.

**Decision:** Strategy behavior, parameters, and assumptions are defined in `docs/strategy-specification.md`. Changes require explicit issue and review; agents must not silently modify parameters.

**Alternatives:** Inline code-only strategy without spec — rejected for auditability.

**Consequences:** Backtester and paper orchestrator must stay aligned with the spec; drift is a defect.

**Issues / PRs:** See strategy-specification git history.

---

## ADR-002 – Risk V1 specification as frozen reference

**Status:** Accepted  
**Date:** Documented in repository (see `docs/risk-specification.md`)

**Context:** Capital and exposure rules must be shared across backtest and paper paths.

**Decision:** Risk limits and kill-switch semantics documented in `docs/risk-specification.md`. V1 kill switch uses FREEZE (no new entries).

**Alternatives:** Per-environment ad hoc limits — rejected.

**Consequences:** Risk engine and paper control plane must match spec; increases require governance approval.

**Issues / PRs:** See risk-specification git history.

---

## ADR-003 – Paper Trading Orchestrator phased delivery (internal phases 1–9)

**Status:** Accepted  
**Date:** Phases 1–9 marked complete in `docs/paper-trading-orchestrator-v1.md`

**Context:** Need production-shaped paper system with PostgreSQL persistence, scheduler, recovery, and API before any live consideration.

**Decision:** Implement orchestrator in documented internal phases 1–9; phase 10 (audit + hardening) is a gate before unsupervised ops.

**Alternatives:** Direct live trading — rejected.

**Consequences:** Live Hyperliquid private API remains out of scope until phase 10 + roadmap P8 approval.

**Issues / PRs:** `services/paper_trading/README.md`

---

## ADR-004 – PostgreSQL as paper trading system of record

**Status:** Accepted  
**Date:** Alembic migrations `001`–`006` in repository

**Context:** Deterministic recovery, advisory locking, and audit trail require durable relational state.

**Decision:** Paper trading state lives in PostgreSQL via SQLAlchemy + Alembic. Single worker enforced with advisory lock.

**Alternatives:** In-memory or file-based state — rejected for production paper path.

**Consequences:** Tests requiring postgres marker; Railway deploy uses managed Postgres plugin.

**Issues / PRs:** `services/paper_trading/db/`

---

## ADR-005 – Railway four-service deployment for paper stack

**Status:** Accepted  
**Date:** Documented in `docs/railway-paper-trading-dashboard-v1.md`

**Context:** Need separated worker, read-only API, dashboard, and database with private networking.

**Decision:** Deploy `paper-trading-worker`, `paper-trading-api`, `paper-trading-dashboard`, and `paper-trading-postgres` on Railway. Only dashboard is public. Config-as-code under `deploy/railway/`.

**Alternatives:** Single monolith service — rejected for blast radius and credential isolation.

**Consequences:** Start commands live in `deploy/scripts/` and must not change without issue.

**Issues / PRs:** `deploy/railway/*.toml`

---

## ADR-006 – ISO weekly candles derived from daily aggregates

**Status:** Accepted  
**Date:** 2026 (commit introducing `_refresh_iso_weekly`, config excluding native `1w` subscription)

**Context:** Native exchange weekly candles may not align with ISO week boundaries required by strategy evaluation.

**Decision:** Do not subscribe to native `1w` stream; derive ISO weekly candles from daily aggregates in `services/market_data/`.

**Alternatives:** Use exchange-native weekly bars — rejected for boundary mismatch.

**Consequences:** Weekly refresh logic and tests must account for derived series; backfill behavior documented in market_data module.

**Issues / PRs:** Recent market_data commits on `cursor/railway-paper-dashboard-v1` branch lineage.

---

## ADR-007 – GitHub as project memory (governance)

**Status:** Accepted  
**Date:** 2026-07-13

**Context:** Roadmap, bugs, and research decisions were spread across chat and scattered docs without unified issue/PR discipline.

**Decision:** Adopt `ROADMAP.md`, `AGENTS.md`, GitHub issue templates, milestones P0–P9, and `scripts/github_project_setup.py`. Chat is workbench only.

**Alternatives:** Notion-only or chat-only tracking — rejected.

**Consequences:** Agents must link PRs to issues; seed issues created for P0–P2 gaps.

**Issues / PRs:** PR #29 (`chore/project-governance`), Issue #2.

---

## ADR-008 – Live / micro-live trading

**Status:** To be decided

**Context:** Roadmap P8 requires separated micro-live system.

**Decision:** *Not yet made.* Live trading remains disabled.

**Alternatives:** Paper-only indefinitely; micro-live on Hyperliquid — TBD.

**Consequences:** TBD upon human approval issue.

---

## ADR-009 – Strategy/Risk V1 parameter inventory and change control

**Status:** Accepted  
**Date:** 2026-07-13

**Context:** Strategy V1 and Risk V1 are frozen references, but parameters can drift when defaults live across docs and code. Research validity requires explicit, published parameters and controlled changes.

**Decision:** Publish a single parameter inventory in `docs/strategy-v1-parameter-inventory.md` derived from the frozen specs and the code defaults. Any parameter change (including defaults, validation maximums, or coupled execution guardrails) requires a dedicated GitHub issue and PR review; changes must update the relevant spec tables and the inventory together.

**Alternatives:** Implicit defaults in code only — rejected for auditability and reproducibility.

**Consequences:** Parameter drift becomes a governance defect. Backtests and paper runs must record the inventory version (commit hash) used.

**Related Issues / PRs:** Issue #4 (Bestehende Strategieparameter dokumentieren und einfrieren).

---

## ADR-010 – Definition of Done adoption

**Status:** Accepted  
**Date:** 2026-07-13

**Context:** `docs/DEFINITION_OF_DONE.md` existed but was not enforced in review. Governance PRs #29, #36, #43 used the PR template DoD section; formal adoption was missing.

**Decision:** Bind DoD to review via PR template, `AGENTS.md`, `docs/PROJECT_OPERATING_SYSTEM.md`, and `docs/DEFINITION_OF_DONE.md` § Review policy. Reviewers must reject PRs lacking test evidence (commands + results) unless explicitly waived in the issue.

**Alternatives:** Wait for CI automation — deferred; manual review policy adopted first.

**Consequences:** Merge without test evidence is a process defect. Optional CI comment remains future work.

**Related Issues / PRs:** Issue #5.

---

## ADR-011 – Solo-maintainer DoD enforcement (interim)

**Status:** Accepted
**Date:** 2026-07-14

**Context:** Issue #5 requires test evidence in post-governance PRs and reviewer rejection of missing test evidence. The repository currently has a single active maintainer; merged PRs #29–#57 have no formal GitHub reviews. Blocking P0 on retroactive reviews would delay governance exit without improving safety.

**Decision:** DoD is enforced in the solo-maintainer phase as follows:

1. Every PR must include the PR template **Tests** section with executed commands and results, or an explicit N/A justification tied to the issue scope.
2. The **Definition of Done** checklist in the PR body must be completed honestly before merge.
3. Governance-related paths are validated by `.github/workflows/github-governance-setup.yml` on pull requests.
4. Formal GitHub review (approve / request changes) becomes mandatory when a second maintainer is added or a reviewer is explicitly assigned on the PR.

**Baseline post-governance PRs with test evidence:** #50, #54, #57 (merged after governance rollout #29).

**DoD checklist in PR body:** first demonstrated in #57; mandatory for all merges from ADR-011 onward. PR template and docs reference DoD since #29.

**Alternatives:** Require retroactive reviews on closed PRs — rejected as performative without adding verification.

**Consequences:** Solo merges without test commands in the PR body remain a process defect. Full reviewer enforcement deferred until team growth; tracked when #52 or staffing changes.

**Related Issues / PRs:** Issue #5, PR #50, PR #54, PR #57.

---

## Template for new entries

```text
ADR-NNN – Title
Status: Proposed / Accepted / Superseded / Rejected
Date:
Context:
Decision:
Alternatives:
Consequences:
Related Issues / PRs:
```

Add new ADRs at the bottom; supersede old ADRs rather than deleting.
