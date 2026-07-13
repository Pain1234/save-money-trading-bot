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

**Status:** Proposed (pending merge of governance PR)

**Date:** 2026-07

**Context:** Roadmap, bugs, and research decisions were spread across chat and scattered docs without unified issue/PR discipline.

**Decision:** Adopt `ROADMAP.md`, `AGENTS.md`, GitHub issue templates, milestones P0–P9, and `scripts/github_project_setup.py`. Chat is workbench only.

**Alternatives:** Notion-only or chat-only tracking — rejected.

**Consequences:** Agents must link PRs to issues; seed issues created for P0–P2 gaps.

**Issues / PRs:** Governance branch `chore/project-governance`.

---

## ADR-008 – Live / micro-live trading

**Status:** To be decided

**Context:** Roadmap P8 requires separated micro-live system.

**Decision:** *Not yet made.* Live trading remains disabled.

**Alternatives:** Paper-only indefinitely; micro-live on Hyperliquid — TBD.

**Consequences:** TBD upon human approval issue.

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
