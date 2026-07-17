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

## ADR-012 – P2 dependency decision for P3 historical data

**Status:** Accepted
**Date:** 2026-07-14

**Context:** P3 (versioned historical market data) requires an operational baseline for database backup and restore when storage ADR selects PostgreSQL. Issue #11 (backup/restore drill) has a completed local restore drill (PR #71 merged) but an outstanding Railway non-production restore.

**Decision:**

The local PostgreSQL restore drill and recovery procedures provide the operational minimum required for P3 planning and implementation.

The outstanding Railway non-production restore in Issue #11 remains mandatory for full P2 completion but does **not** block local P3 historical-data development.

P3 changes must not depend on untested Railway restore behavior.

**Alternatives:** Block all P3 work until Railway restore is proven — rejected; local drill satisfies planning and implementation risk for dataset work.

**Consequences:** #11 stays open on the P2 milestone. Epic #45 and P3 sub-issues may proceed. Any P3 storage implementation that shares PostgreSQL must document backup/restore assumptions explicitly.

**Related Issues / PRs:** Issue #11, Issue #45, PR #71, `docs/P3_HISTORICAL_DATA_PLAN.md`.

---

## ADR-013 – Immutable dataset storage (hybrid PostgreSQL + filesystem)

**Status:** Accepted
**Date:** 2026-07-14

**Context:** P3 requires append-only dataset catalog, immutable raw provider payloads, and normalized candle persistence (#79). Options: PostgreSQL only, filesystem/object store only, or hybrid. Paper trading already uses Railway PostgreSQL (ADR-004); local backup/restore drill exists (ADR-012, #71).

**Decision:** Adopt a **hybrid** storage architecture:

1. **PostgreSQL** (shared paper DB, new `market_data_*` tables only): dataset manifest catalog, normalized candle rows, quarantine/quality metadata references. Append-only by convention: no `UPDATE`/`DELETE` on published dataset rows; corrections insert new `dataset_id` with `parent_dataset_id`.
2. **Filesystem** (configurable `MARKET_DATA_DATASET_ROOT`): content-addressed raw JSON artifacts at `raw/{sha256}.json`. Immutable: write-if-not-exists; hash verified on read.
3. **Lookup:** Research and import tooling resolve `dataset_id` via PostgreSQL catalog; raw bytes loaded by `raw_content_hash` / path.

**Alternatives considered:**

| Option | Rejected because |
|--------|------------------|
| PostgreSQL only (bytea blobs) | Large raw payloads bloat DB backups and migration cost |
| Filesystem only | No transactional catalog alongside paper trading; weaker query by `dataset_id` |
| Separate database | Extra Railway service and backup scope for solo-maintainer phase |

**Backup/restore impact (R-009):**

- PostgreSQL tables included in existing `pg_dump` / restore drill scope.
- Raw files require `MARKET_DATA_DATASET_ROOT` volume backup documented in storage runbook addendum (#79).
- P3 must not depend on untested Railway restore (#11 waiver per ADR-012).

**Consequences:** Alembic migration `010` adds market-data tables only; paper-trading tables untouched. Import pipeline (#80) writes raw files before normalization.

**Related Issues / PRs:** Issue #78, Issue #79, `docs/market-data-contract.md`.

---

## ADR-014 – One Hyperliquid multi-asset platform with asset-specific profiles

**Status:** Accepted
**Date:** 2026-07-15

**Context:** The roadmap expands beyond BTC/ETH/SOL crypto perpetuals to HIP-3 equity, index, and commodity perpetuals on the same Hyperliquid ecosystem. A governance decision is needed on repository boundaries, asset modeling, and phase gates before any implementation.

**Decision:**

1. Crypto, equity, index, and commodity **perpetuals** are supported within the **same** research and paper-trading platform (single repository unless future technical or regulatory limits prove otherwise).
2. Asset-class differences are modeled via **asset metadata profiles**, provider/DEX configuration, cost/funding models, and risk profiles — not by treating all symbols identically.
3. Planned profile types: `CRYPTO_24_7`, `HIP3_EQUITY_PERP`, `HIP3_INDEX_PERP`, `HIP3_COMMODITY_PERP`.
4. Equity/index/commodity exposure is **synthetic perpetual exposure**; the system must not describe these as holding real shares or physical commodities.
5. **P7** allows research, backtest, shadow, and paper only. **P8 live trading** still requires human approval.
6. Multi-asset expansion must **not** bypass **P5** (validation) or **P6** (paper soak).
7. Architectural split into separate repositories is required only if evidenced by technical or regulatory constraints.

**Alternatives:**

| Option | Rejected because |
|--------|------------------|
| Separate repo per asset class | Duplicates research, risk, and monitoring infrastructure |
| Single undifferentiated asset model | Ignores funding, oracle, session, and corporate-action differences |

**Consequences:**

- Asset profiles become mandatory before new markets trade in paper or live paths.
- Costs and risks must be validated per profile.
- P7 milestone renamed to **Multi-Asset and Independent Strategy Candidates**.
- Planning issues for metadata contract, HIP-3 equity validation, and correlated exposure model are tracked on P7; implementation is out of scope until those gates pass.

**Related Issues / PRs:** `ROADMAP.md` § P7, `docs/ARCHITECTURE.md` § Multi-asset target architecture, P7 planning issues (governance setup).

---

## ADR-015 – Retire Codex review gate

**Status:** Accepted

**Date:** 2026-07-17

**Context:** The read-only Codex review gate (Issue #149, `.agent-loop/`) blocked productive Windows workflows (OS isolation fail-closed), added high operational cost, and did not improve merge safety enough to justify keeping it.

**Decision:** Remove the Codex review gate and all mandatory Codex-approval requirements. Quality gate is: implement → tests → CI → human merge. Agents must not auto-merge or auto-deploy.

**Alternatives:** Keep gate with WSL/CI-only APPROVED — rejected as too costly relative to value.

**Consequences:**

- `.agent-loop/`, `tests/agent_loop/`, and `00-mandatory-codex-review.mdc` are removed.
- CI path classifier no longer has an `agent_loop` slice.
- Label `agent:codex-review` is no longer seeded by governance setup.
- Issue #149 is closed as superseded by this retirement.

**Related Issues / PRs:** #149; PR for `chore/remove-codex-review-gate`.

---

## ADR-016 – Enforce main required checks via repository rulesets

**Status:** Accepted

**Date:** 2026-07-17

**Context:** Classic branch protection API returns HTTP 403 on this private
repository without GitHub Pro (#65). A repository ruleset on `main` already
blocked deletion/force-push and required PRs, but did not require CI checks.

**Decision:** Complete #65 by adding the Phase-1 required status check contexts
(`validate`, `requirements-baseline`, `lint`, `test`, `test-market-data`,
`test-deploy`, `postgres`) to ruleset `main` (id 19091297) with strict policy.
Do not claim classic branch protection is enabled.

**Alternatives:** Upgrade to GitHub Pro for classic protection; make the repo
public — rejected as unnecessary once rulesets enforce the same checks.

**Consequences:** Docs (`docs/branch-protection.md`, `docs/baseline-paper-v1.md`)
describe rulesets as the source of truth. Phase 2 may retarget check names per
`docs/ci/REQUIRED_CHECK_MIGRATION.md`.

**Related Issues / PRs:** #65

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
