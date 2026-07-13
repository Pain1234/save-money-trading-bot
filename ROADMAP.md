# Research and Operations Roadmap

Central project goal:

> Not to program the perfect trading bot, but to build a system that reliably filters out bad strategies, credibly identifies good strategies, measures real execution deviations, and never risks more capital than the proven maturity level justifies.

**Governance source of truth:** GitHub (issues, milestones, pull requests, decision log). Chat and Cursor sessions are a workbench, not the project memory.

**Relationship to internal implementation phases:** The paper-trading orchestrator was delivered in internal phases 1–9 (see `docs/paper-trading-orchestrator-v1.md`). Phase 10 (audit and hardening) remains open. The roadmap below (P0–P9) governs **research maturity, operational reliability, and capital deployment** — it is not a 1:1 map to those internal phases.

---

## Status overview

| Phase | Name | Status | Human approval required |
|-------|------|--------|-------------------------|
| **P0** | Governance and Scope Freeze | **Active (in progress)** | No |
| P1 | Reproducible Baseline Release | Next | No |
| P2 | Operational Reliability | In flight (partial; not exit-complete) | No |
| P3 | Versioned Historical Market Data | Not started | No |
| P4 | Research Engine | Partial (backtester exists; not standardized pipeline) | No |
| P5 | Honest Validation of Trend Strategy V1 | Not started | No |
| P6 | Paper Trading Soak | Not started (Railway paper deploy in progress) | No |
| P7 | Independent Strategy Candidates | Not started | No |
| P8 | Separate Micro-Live System | Blocked | **Yes — explicit human approval** |
| P9 | Controlled Scaling | Blocked | **Yes — explicit human approval** |

**Evidence for current assessment (2026-07):**

- Paper-trading orchestrator phases 1–9 implemented; phase 10 audit gate not closed (`services/paper_trading/README.md`, `docs/paper-trading-orchestrator-v1.md`).
- Railway four-service deployment documented; production soak not yet at 90 days (`docs/railway-paper-trading-dashboard-v1.md`).
- Recent operational work: heartbeat observability, reconnect readiness, advisory-lock hardening, ISO weekly candles from daily aggregates — indicates **P2 work in progress**, not P2 exit.
- No `.github/` CI, no formal baseline release tag — **P1 not complete**.
- Governance docs merged via PR #29; setup script idempotent apply verified (Issue #2) — **P0 governance baseline in place**; remaining P0 items tracked in milestone issues (#3–#5).
- Live trading, wallet signing, and real exchange orders explicitly **not implemented** (`services/paper_trading/README.md`).

---

## P0 – Governance and Scope Freeze

**GitHub milestone:** `P0 – Governance and Scope Freeze`

### Goal

Establish binding project memory in GitHub: roadmap, issue/PR process, responsibilities, scope boundaries, frozen strategy parameters, and no uncontrolled functional changes.

### Scope

- `ROADMAP.md`, `AGENTS.md`, `CHANGELOG.md`
- `docs/PROJECT_OPERATING_SYSTEM.md`, `docs/DEFINITION_OF_DONE.md`, templates
- `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`
- `.cursor/rules/project-governance.mdc`
- `scripts/github_project_setup.py` (labels, milestones, seed issues)
- Initial decision log and risk register (evidence-based only)

### Non-scope

- Trading logic, strategy parameters, migrations, production start commands
- CI implementation (document gap only)
- Live trading activation

### Prerequisites

- Repository with existing specs (`docs/strategy-specification.md`, `docs/risk-specification.md`, etc.)

### Deliverables

- All governance files merged to `main`
- GitHub labels and milestones created
- Seed P0/P1/P2 issues created
- Strategy parameters documented and marked frozen (separate issue)

### Exit criteria

- [ ] All governance files present on `main`
- [ ] GitHub issue templates and PR template active
- [ ] Definition of Done documented and referenced in PR template
- [ ] First milestones and seed issues created via setup script
- [ ] Agents and Cursor rules point to GitHub as source of truth

### Stop criteria

- Governance PR blocked > 30 days without review → escalate human decision on ownership

### Risks

- Documentation drift if GitHub issues not used after setup
- Duplicate/conflicting docs if old files not cross-linked

---

## P1 – Reproducible Baseline Release

**GitHub milestone:** `P1 – Reproducible Baseline Release`

### Goal

Current paper-trading stack reproducible from a tagged commit: pinned dependencies, documented start commands, documented tests, possible baseline release tag.

### Scope

- Document worker/API/dashboard start paths (`deploy/scripts/`, `deploy/railway/`)
- Pin or document Python/Node versions (`pyproject.toml`, Dockerfiles)
- Document test commands and markers (`postgres`, `live`, `soak`)
- Define baseline tag criteria (no new features; known test baseline)

### Non-scope

- New features, strategy changes, live trading

### Prerequisites

- P0 exit criteria met

### Deliverables

- Baseline release tag (e.g. `baseline-paper-v1.x`)
- Updated README aligned with actual architecture (not mock-data placeholder)
- Dependency/version manifest or documented lock strategy

### Exit criteria

- [ ] Tag exists; checkout + documented commands reproduce paper worker locally or in CI
- [ ] Test suite documented; known failures/flakes recorded
- [ ] Start commands unchanged from production paths (documentation only)

### Stop criteria

- Cannot reproduce tests without PostgreSQL → document minimum environment; do not claim exit

### Risks

- README still describes mock data while production uses PostgreSQL/Railway
- No GitHub Actions CI today — reproducibility is manual

---

## P2 – Operational Reliability

**GitHub milestone:** `P2 – Operational Reliability`

### Goal

Backup/restore, readiness/heartbeat, reconciliation, idempotent processing, restart after crash, incident and runbook structure.

### Scope

- Heartbeat and readiness (`services/paper_trading/readiness.py`, `heartbeat.py`)
- Recovery and advisory lock (`recovery.py`, `lock.py`, `runtime.py`)
- Reconnect and market-data degraded mode (`services/market_data/`)
- Runbook stubs and incident templates
- Railway deployment reliability (config-as-code under `deploy/railway/`)

### Non-scope

- Live execution, capital scaling

### Prerequisites

- P1 baseline documented

### Deliverables

- Verified backup/restore procedure for PostgreSQL
- Reconciliation checks documented and tested
- Runbooks for worker stop, deploy verify, incident response
- Critical metrics defined (heartbeat age, readiness state, reconnect count)

### Exit criteria

- [ ] Backup and restore tested once and documented
- [ ] Daily reconciliation procedure documented
- [ ] Worker restart after kill tested; no duplicate entries/fills
- [ ] Incident template used for at least one table-top or real S3+ event
- [ ] Runbooks cover paper worker, API, dashboard, kill switch

### Stop criteria

- Repeated S1/S2 incidents without postmortem → freeze new features until P2 gaps closed

### Risks

- Single replica worker — advisory lock mitigates but ops mistakes remain S1
- Market-data reconnect edge cases (recent fixes; full suite may show postgres isolation failures in bulk runs)

**Current gap:** Backup/restore and formal reconciliation runbooks not yet complete; substantial code exists.

---

## P3 – Versioned Historical Market Data

**GitHub milestone:** `P3 – Versioned Historical Market Data`

### Goal

Persistent historical store with gap/duplicate detection, dataset manifests, data versions, plausibility checks, reproducible imports.

### Scope

- `services/market_data/` persistence and backfill
- Dataset manifests and version IDs
- Import reproducibility

### Non-scope

- Live trading data paths beyond paper needs

### Prerequisites

- P1 baseline; P2 operational minimum for data pipeline restarts

### Deliverables

- Versioned dataset catalog
- Gap and duplicate detection reports
- Reproducible import scripts with manifest output

### Exit criteria

- [ ] Each research dataset has manifest (hash, range, symbols, source)
- [ ] Re-import produces identical aggregates for fixed version
- [ ] Gap/duplicate audit documented

### Stop criteria

- Unexplained gaps in production candle chain → block P5 research until resolved

### Risks

- Exchange API changes; ISO weekly derivation from daily (recent ADR) adds complexity

**Current gap:** Live ingestion exists; full versioning/manifest pipeline not implemented.

---

## P4 – Research Engine

**GitHub milestone:** `P4 – Research Engine`

### Goal

Standardized strategy interfaces, reproducible experiments, experiment registry, benchmarks, cost model, unified result reports.

### Scope

- `services/backtester/`, `services/strategy_engine/`, `services/risk_engine/`
- `docs/EXPERIMENT_TEMPLATE.md`, experiment issues
- Cost and slippage assumptions documented per experiment

### Non-scope

- Production paper worker changes for research convenience

### Prerequisites

- P3 data versioning (or explicit dataset snapshot for each experiment)

### Deliverables

- Experiment ID scheme and registry location
- Standard report format
- Benchmark definitions

### Exit criteria

- [ ] Every experiment traceable to commit + dataset version + config
- [ ] Acceptance/rejection criteria applied consistently
- [ ] Old results immutable; invalidation process used

### Stop criteria

- Overfitting detected without OOS discipline → halt new strategy promotion

### Risks

- Backtest bias; cost model optimism

**Current gap:** Backtester and specs exist; unified experiment registry and pipeline not enforced.

---

## P5 – Honest Validation of Trend Strategy V1

**GitHub milestone:** `P5 – Honest Validation of Trend Strategy V1`

### Goal

Untouched out-of-sample test, walk-forward, cost stress, parameter stability, bootstrap/Monte Carlo, documented accept/reject criteria for Strategy V1 (`docs/strategy-specification.md`).

### Scope

- Research only; **no strategy parameter changes** without explicit issue + approval
- Results stored as experiment artifacts

### Non-scope

- New strategies; live trading

### Prerequisites

- P4 experiment pipeline; frozen parameters (P0 issue)

### Deliverables

- OOS report with frozen holdout
- Walk-forward and stress reports
- Documented accept/reject decision

### Exit criteria

- [ ] OOS never used for tuning
- [ ] All robustness tests completed or explicitly waived with rationale
- [ ] Human sign-off on accept/reject recorded in decision log

### Stop criteria

- Strategy fails OOS or stress → reject for paper/live promotion; no parameter fishing

### Risks

- Strategy overfitting; regime change

**Current gap:** Not started as formal gated validation.

---

## P6 – Paper Trading Soak

**GitHub milestone:** `P6 – Paper Trading Soak`

### Goal

≥ 90 days stable paper operation with daily reconciliation, funding/mark price observation, paper-to-live decay measurement, documented operational incidents.

### Scope

- Railway paper stack (`bot.save-money.xyz` dashboard, worker, API, Postgres)
- Monitoring and incident logging

### Non-scope

- Real orders; capital at risk

### Prerequisites

- P5 accept decision (or explicit waiver documented)
- P2 operational minimum

### Deliverables

- Soak log (daily reconciliation, heartbeat, readiness)
- Decay metrics vs backtest
- Incident register entries

### Exit criteria

- [ ] 90 consecutive days without unresolved S1
- [ ] Daily reconciliation completed and archived
- [ ] Paper-to-live decay documented with assumptions

### Stop criteria

- S1 during soak → pause promotion clock until root cause closed

### Risks

- Paper fill model ≠ live fills; funding/slippage drift

**Current gap:** Deployment in progress; 90-day soak not started.

---

## P7 – Independent Strategy Candidates

**GitHub milestone:** `P7 – Independent Strategy Candidates`

### Goal

Independent strategy hypotheses (not merely correlated alt coins); each through same research pipeline; no unreviewed simultaneous activation.

### Scope

- New hypotheses as research issues
- Correlation budget documented

### Non-scope

- Parallel live activation

### Prerequisites

- P4 pipeline; P6 soak learnings

### Exit criteria

- [ ] Each candidate has experiment chain through P5-equivalent gates
- [ ] Correlation to V1 measured
- [ ] At most one new candidate in paper at a time unless ADR approves

### Stop criteria

- High correlation cluster → reject diversification claim

**Current gap:** Not started.

---

## P8 – Separate Micro-Live System

**GitHub milestone:** `P8 – Separate Micro-Live System`

**Blocked until explicit human approval.**

### Goal

Technically separated live execution, minimal API permissions, bounded capital, exchange reconciliation, kill switch, real fill/fee/funding data.

### Scope

- Separate deployment from paper
- Micro capital only

### Non-scope

- Scaling; strategy changes

### Prerequisites

- P6 exit; P2 kill switch verified; security review; **human approval issue**

### Exit criteria

- [ ] Live system isolated from paper DB and credentials
- [ ] Kill switch tested in production micro environment
- [ ] Reconciliation matches exchange within defined tolerance

### Stop criteria

- Any S1 → immediate halt; revert to paper only

### Risks

- Exchange, key compromise, fat finger

**Current gap:** Live execution explicitly not implemented.

---

## P9 – Controlled Scaling

**GitHub milestone:** `P9 – Controlled Scaling`

**Blocked until explicit human approval after P8.**

### Goal

Scale only on real evidence: capital limits, drawdown limits, correlation budget, documented downgrade rules, economic viability proof.

### Prerequisites

- P8 micro-live evidence; **human approval**

### Exit criteria

- [ ] Scaling rules in risk spec enforced in code
- [ ] Drawdown breach triggers automatic downgrade
- [ ] Documented economic review

**Current gap:** Not applicable until P8.

---

## How to use this roadmap

1. Pick the **active phase** milestone in GitHub.
2. Create or select an **issue** with scope, non-scope, and acceptance criteria.
3. One branch / one PR per issue (`docs/PROJECT_OPERATING_SYSTEM.md`).
4. Update this file only when phase status changes with evidence (link PR/issue).
