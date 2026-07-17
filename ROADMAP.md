# Research and Operations Roadmap

Central project goal:

> Not to program the perfect trading bot, but to build a system that reliably filters out bad strategies, credibly identifies good strategies, measures real execution deviations, and never risks more capital than the proven maturity level justifies.

**Governance source of truth:** GitHub (issues, milestones, pull requests, decision log). Chat and Cursor sessions are a workbench, not the project memory.

**Relationship to internal implementation phases:** The paper-trading orchestrator was delivered in internal phases 1–9 (see `docs/paper-trading-orchestrator-v1.md`). Phase 10 (audit and hardening) remains open. The roadmap below (P0–P9) governs **research maturity, operational reliability, and capital deployment** — it is not a 1:1 map to those internal phases.

---

## Status overview

| Phase | Name | Status | Human approval required |
|-------|------|--------|-------------------------|
| **P0** | Governance and Scope Freeze | **Complete** | No |
| **P1** | Reproducible Baseline Release | **Complete** (post-tag follow-ups in PR #63) | No |
| P2 | Operational Reliability | In flight (partial; exit criteria not all met) | No |
| P2.5 | Dashboard Performance & Responsiveness | Not started | No |
| **P3** | Versioned Historical Market Data | **Complete** | No |
| P4 | Research Engine und Research Workspace V1 | **In flight** (engine + read UI; Strategy Lab/start #242) | No |
| P5 | Honest Validation of Trend Strategy V1 | **Planning** (honest validation protocol; no OOS opened) | No |
| P6 | Paper Trading Soak | Not started (Railway paper deploy in progress) | No |
| P7 | Multi-Asset and Independent Strategy Candidates | Not started (planning only) | No |
| P8 | Separate Micro-Live System | Blocked | **Yes — explicit human approval** |
| P9 | Controlled Scaling | Blocked | **Yes — explicit human approval** |

**Evidence for current assessment (2026-07):**

- Paper-trading orchestrator phases 1–9 implemented; phase 10 audit gate not closed (`services/paper_trading/README.md`, `docs/paper-trading-orchestrator-v1.md`).
- Railway four-service deployment documented; production soak not yet at 90 days (`docs/railway-paper-trading-dashboard-v1.md`).
- P2 in progress (2026-07-14): metrics catalog, idempotency audit, reconciliation procedure, worker restart CI evidence, tabletop INC-20260714-001, runbook index promoted. **Local** restore drill with committed trade data passed (#11); **Railway non-prod restore drill open** (#11). Kill-switch production path is worker stop (control API off on Railway).
- Governance workflow merged (PR #54); CI workflow in `.github/workflows/ci.yml` (#53); branch protection on `main` (#65).
- Default branch **`main`** (migrated 2026-07-14, Issue #64); rollback branch `cursor/railway-paper-dashboard-v1` retained.
- **P0 complete** (2026-07-14): exit criteria met with documented deviations (#52 `main`, ADR-011 solo-maintainer DoD enforcement). Attributed to PRs #51/#54/#57 and follow-up governance work — **not** PR #55 (baseline docs only).
- **P1 complete** (2026-07-14): tag `baseline-paper-v1.0.0` at `daacb627` (PR #62 merge). Post-tag doc/lock/CI improvements tracked in PR #63 (optional `baseline-paper-v1.0.1` after merge).
- **P3 complete** (2026-07-14): versioned historical market data pipeline implemented (`services/market_data/`, migration `010_market_data_datasets`, issues #76–#84); reproducibility audit in `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md`.
- Dashboard UI locally usable with real paper data (login, wallet, PnL, positions, fills, equity); **not** yet classified as production-accepted performant monitoring (`docs/railway-paper-trading-dashboard-v1.md` maturity levels).
- **P4** engine complete; Research Workspace read-only browse (#240) and Strategy Lab + start (#242) on `main` / in flight. Compare/robustness/gates remain open — see `docs/project-management/p4-research-workspace-follow-ups.md`. **P5 blocked** until Engine + API + Workspace are jointly usable enough.
- **P2.5** milestone and seed issues defined for dashboard/API performance baseline, instrumentation, and production acceptance (governance only — no runtime optimization yet).
- **P7** renamed to Multi-Asset and Independent Strategy Candidates; HIP-3 equity/index/commodity perpetuals and asset profiles documented in ADR-014 (`docs/DECISION_LOG.md`); planning issues only.
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

- [x] Governance files present on default branch; main migration governed by Issue #52
- [x] GitHub issue templates and PR template active (PR #29, #54)
- [x] Definition of Done documented, referenced in PR template, enforced per ADR-011 (Issue #5; test evidence #50/#54/#57, DoD section demonstrated #57)
- [x] First milestones and seed issues created via setup script (PR #54, sequential idempotency tested)
- [x] Agents and Cursor rules point to GitHub as source of truth (`AGENTS.md`, `.cursor/rules/project-governance.mdc`)

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

- [x] Start paths documented from `deploy/scripts/` (`docs/baseline-paper-v1.md`)
- [x] Python 3.12 / Node 22 / PostgreSQL 16 recorded
- [x] Test suite and markers documented; known local failure recorded and resolved (#58)
- [x] Tag exists (`baseline-paper-v1.0.0` at `daacb627`, PR #62)
- [x] CI workflow exists and runs core gates (Issue #53); not all 782 tests run in CI — see baseline doc; branch protection enforcement pending

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

- [x] Backup and restore tested once and documented — **local** Docker drill with committed trade data and snapshot compare (2026-07-14, `docs/runbooks/backup-restore.md`)
- [ ] Railway non-prod PostgreSQL restore drill (Issue #11 scope; account Backups tab showed no snapshots 2026-07-14)
- [x] Daily reconciliation procedure documented — `docs/runbooks/reconciliation-daily.md` + `scripts/reconcile_accounting.py` (weekly minimum for solo ops)
- [x] Worker restart after kill tested; no duplicate entries/fills — CI `postgres` e2e/failure/replay tests + `docs/runbooks/worker-restart.md`
- [x] Incident template used for at least one table-top or real S3+ event — `docs/incidents/INC-20260714-001-tabletop-duplicate-fill.md`
- [ ] Runbooks cover paper worker, API, dashboard, kill switch — worker/API/dashboard complete; kill switch **partial** (production = worker stop; control API local/dev only)

### Stop criteria

- Repeated S1/S2 incidents without postmortem → freeze new features until P2 gaps closed

### Risks

- Single replica worker — advisory lock mitigates but ops mistakes remain S1
- Market-data reconnect edge cases (recent fixes; full suite may show postgres isolation failures in bulk runs)

### Issue #48 disposition

R-004 backtester–paper parity ([#48](https://github.com/Pain1234/save-money-trading-bot/issues/48)) is **research scope**, not operational reliability. GitHub milestone moved to **P4 – Research Engine**; partial coverage remains via phase 9 / replay tests.

**P2 ops artifacts (in progress):** `docs/operations/metrics.md`, `docs/operations/idempotency-audit.md`, runbooks under `docs/runbooks/`.

**Current gap:** Railway non-prod restore drill not executed (Issue #11); account Backups UI showed no snapshots 2026-07-14. Kill-switch runbook partial (production = Railway worker stop; control API local/dev only).

---

## P2.5 – Dashboard Performance & Responsiveness

**GitHub milestone:** `P2.5 – Dashboard Performance & Responsiveness`

### Goal

The existing dashboard and read-only API receive measurable performance targets, runtime instrumentation, controlled caching, visible loading states, and automated regression tests.

### Prerequisites

- Reproducible P1 baseline
- Usable read-only API
- Usable Next.js dashboard
- Basic P2 readiness and operational metrics

### Scope

- Dashboard performance baseline
- Server render time
- Next.js-to-FastAPI latency
- FastAPI processing time
- SQL latency and query count
- Response size
- Cold and warm requests
- Controlled short-term caching
- Loading states and streaming
- API summary for overview
- Database index review
- Performance and navigation tests
- Production dashboard acceptance

### Non-scope

- Strategy changes
- New trading rules
- Live trading
- Wallet signing
- New coins or HIP-3 assets
- Cosmetic redesign only
- Migration to another frontend framework
- Blind Railway resource scaling without measurement

### Initial performance targets

Start budgets — confirm or adjust after real baseline measurement via documented decision.

| Target | Budget |
|--------|--------|
| Overview warm | p95 under 1.5 s |
| Dashboard page navigation | visible content p95 under 1.5 s |
| `/api/v1/status` | p95 under 250 ms |
| `/api/v1/wallet` | p95 under 250 ms |
| Table endpoints | p95 under 500 ms |
| API unreachable feedback | visible within 2–3 s |
| Normal dashboard SQL query | under 250 ms |
| Performance regression | none unmonitored |

### Deliverables

- Documented performance baseline artifact
- Request timing and DB query instrumentation
- Dashboard summary API endpoint (read-only)
- Documented cache policy
- Loading states on all relevant routes
- SQL/index audit with `EXPLAIN ANALYZE`
- Automated performance regression checks
- Production dashboard acceptance record

### Exit criteria

- [ ] Baseline measurement for all major pages and endpoints documented
- [ ] Server, API, and DB portions separately measurable
- [ ] Overview uses a single aggregated API request where possible
- [ ] Redundant runtime/status DB reads identified and removed or justified
- [ ] Loading states exist for all relevant dashboard routes
- [ ] Short-term caches documented and tested
- [ ] Dashboard queries reviewed with `EXPLAIN ANALYZE`
- [ ] Required composite indexes documented or implemented
- [ ] Automated performance test or budget check runs in CI
- [ ] Production dashboard acceptance documented
- [ ] Measured values meet agreed budgets or documented waiver in decision log

### Stop criteria

- No optimization without prior measurement
- No Railway resource increase as first remedy
- No complex cache infrastructure when query/render is root cause
- No UI expansion while core pages exceed performance budget

### Risks

- Dashboard latency may mask critical status changes (R-019)
- Uncontrolled caching may show stale readiness (R-021)
- Growing history tables slow unindexed queries (R-020)

**Current gap:** Dashboard functional but subjectively slow; performance baseline and production acceptance not completed.

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

- [x] Each research dataset has manifest (hash, range, symbols, source) — `DatasetManifest` (#77), import pipeline (#80)
- [x] Re-import produces identical aggregates for fixed version — `test_historical_import.py`, `test_aggregation_manifest.py`
- [x] Gap/duplicate audit documented — `dataset_quality.py` (#81), `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md` (#84)

### Stop criteria

- Unexplained gaps in production candle chain → block P5 research until resolved

### Risks

- Exchange API changes; ISO weekly derivation from daily (recent ADR) adds complexity

**Status:** Complete (2026-07-14). Evidence: `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md`, `services/market_data/`, issues #76–#84.

**Planning document:** [`docs/P3_HISTORICAL_DATA_PLAN.md`](docs/P3_HISTORICAL_DATA_PLAN.md).

---

## P4 – Research Engine und Research Workspace V1

**GitHub milestone:** `P4 – Research Engine` (extend / rename toward Research Workspace V1)

### Goal

Standardized strategy interfaces, reproducible experiments, experiment registry,
benchmarks, cost model, unified result reports — **and** a dashboard Research
Workspace that reads those artifacts without introducing a second research system.

### Scope

- `services/backtester/`, `services/strategy_engine/`, `services/risk_engine/`
- `services/research/` (Spec, runner, registry, metrics, costs, benchmarks)
- Read-only Research API + Dashboard Research UI (overview / list / detail)
- `docs/EXPERIMENT_TEMPLATE.md`, experiment issues
- Cost and slippage assumptions documented per experiment

### Non-scope (this milestone still open)

- Cancel / Retry / Re-run lifecycle (explicitly deferred)
- Durable multi-process job queue (Celery/Redis) — V1 uses in-process threads
- Compare View, Robustness Lab orchestration UI (follow-up)
- Gate Evaluator persistence / promotion controls (follow-up)
- New Experiment Postgres tables; second registry; live/paper order actions from Research

### Prerequisites

- P3 data versioning (or explicit dataset snapshot for each experiment)

### Deliverables

#### Engine (done)

- [x] Experiment ID scheme and registry location (`registry.jsonl`)
- [x] Standardized strategy interfaces / resolver contract
- [x] Standard report format + metrics artifacts
- [x] Benchmark definitions (`benchmark_id` / version, calculation, period/dataset/cost parity)
- [x] Cost model field/version enforcement (stress evaluation is P5/P4.7 follow-up)
- [x] Documented invalidation workflow for historical results

#### Research Workspace — read-only slice (#240)

- [x] Thin read API over ExperimentRegistry + run artifacts (`/api/v1/research/...`)
- [x] Monitor / Research navigation; routes under `/dashboard/research`
- [x] Overview, experiment list (search/filter), experiment detail (metadata, config, metrics, equity/drawdown)
- [x] Missing values as „Nicht verfügbar“ / controlled errors; no productive mock data
- [x] Path-traversal protection; unknown experiment → 404; no live-order access from Research

#### Research Workspace — Strategy Lab + start (#242)

- [x] Strategy Lab route `/dashboard/research/experiments/new`
- [x] Write API: strategies/schema/datasets, create, start, status (POST allow-listed on private dashboard API)
- [x] Filesystem `ResearchJobStore` + in-process worker wrapping `run_experiment` (no Celery/Redis)
- [x] Same Spec/Runner/Registry/artifacts as CLI; atomic created→queued CAS; terminal create idempotent (no implicit Re-run); stale queued/running after restart fail-closed
- [x] Detail job panel with polling; Overview CTA „Neues Experiment“

#### Still open (separate issues — see `docs/project-management/p4-research-workspace-follow-ups.md`)

- [ ] P4.7 Experiment- und Strategie-Vergleich
- [ ] P4.7 Robustness-Orchestrierung
- [ ] P4.7 Versionierter Gate Evaluator und Gate-Persistenz
- [ ] P4.8 End-to-End-, Reproduzierbarkeits- und UI-Abnahmetests
- [ ] Cancel / Retry / Re-run (explicitly deferred)

### Binding dependency chain

```
P3 → #141 → #142 → {#144, #49, #148} → #143 → {#48, #145} → #146 → #147 → engine done
→ #240 read-only workspace → #242 Strategy Lab + start → P4.7…P4.8 → P4 done → P5
```

Docs preparation may run in parallel from #142.

### Exit criteria

- [x] Every experiment traceable to commit + dataset version + config
- [x] Acceptance/rejection criteria applied consistently (process/DoD; enforced via issue/PR template — ongoing discipline)
- [x] Old results immutable; invalidation via registry and/or append-only sidecar only (`invalidated` status, reason, provenance, replacement run; original RunManifest unchanged)
- [x] P5 gates (OOS / walk-forward / cost-stress robustness) not pre-empted
- [x] Research Workspace usable for browsing real experiments (API + UI) without a parallel system
- [ ] Lab / async runs / compare / robustness / gates delivered or explicitly deferred with issues

### Stop criteria

- Overfitting detected without OOS discipline → halt new strategy promotion

### Risks

- Backtest bias; cost model optimism; UI inventing metrics not produced by the engine

**Current gap:** Engine + read-only workspace on `main`. Strategy Lab + start (#242) in flight.
Compare, robustness orchestration, and gate evaluator remain open.
**P5 remains blocked** until Engine, Read-API, and Workspace are jointly usable enough.

---

## P5 – Honest Validation of Trend Strategy V1

**GitHub milestone:** `P5 – Honest Validation of Trend Strategy V1`

### Goal

Honestly decide whether frozen Strategy V1 warrants promotion evidence for P6 — not prove profitability. Allowed outcomes only: `ACCEPT_FOR_P6`, `REJECT`, `INCONCLUSIVE` (`INCONCLUSIVE` is not promotion). Planning and gates: [`docs/research/p5/`](docs/research/p5/README.md).

### Scope

- Research only; **no strategy parameter changes** under Strategy V1 without new version + new freeze
- Data-exposure audit, candidate freeze, pre-registered protocol, walk-forward, cost stress, parameter stability, bootstrap/Monte Carlo, one-shot untouched OOS
- Results stored as **private-edge** experiment artifacts (#181); public repo keeps methodology/templates only

### Non-scope

- New strategies; new assets / HYPE / HIP-3; paper soak (P6); live trading; optimizing thresholds after seeing OOS

### Prerequisites

- P4 research engine + usable Research Workspace (read API + browse UI at minimum; Lab/async as needed for P5 workflow)
- #181 public/private separation complete before first real P5 result
- Signed candidate freeze + validation protocol **before** opening final holdout

### Binding issue chain

```text
#181 → #196 → #197 → #198 → #199 → {#200…#203} → human pre-OOS → #204 → #205
```

Canonical risk: [#47](https://github.com/Pain1234/save-money-trading-bot/issues/47). Canonical boundary: [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181).

### Deliverables

- Planning pack under `docs/research/p5/` (templates; no simulated results)
- Frozen holdout + one-shot OOS report (private)
- Walk-forward, cost-stress, stability, uncertainty reports (private)
- Documented `ACCEPT_FOR_P6` / `REJECT` / `INCONCLUSIVE` in decision log

### Exit criteria

- [ ] Strategy V1 uniquely frozen; exposure audited; protocol frozen before OOS view
- [ ] Benchmarks + sample-sufficiency + decision rules pre-registered
- [ ] Walk-forward, cost stress, parameter stability completed; bootstrap/MC completed or methodically N/A
- [ ] Final OOS evaluated exactly once; no post-hoc parameter fishing; no leakage
- [ ] Outcome documented; human sign-off in decision log; #47 closed; #181 satisfied
- [ ] No new strategy/assets; no P6/P8 pre-emption; no live-trading code

Full checklist: `docs/research/p5/P5_EXECUTION_CHECKLIST.md`.

### Stop criteria

- Leakage, unclear dataset, freeze violation, unreproducible results, missing costs, public leak of private results, critical P4 defect, or retuning after failed OOS → halt; no promotion; human decision

### Risks

- Strategy overfitting; regime change; false OOS claims; public/private leakage

**Current gap:** Planning documents and issue chain in progress; **no** final holdout opened; **no** formal V1 OOS decision yet.

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

## P7 – Multi-Asset and Independent Strategy Candidates

**GitHub milestone:** `P7 – Multi-Asset and Independent Strategy Candidates`

**Planning only** — no multi-asset implementation until P5 validation and P6 paper soak complete (ADR-014).

### Goal

Expand beyond BTC/ETH/SOL to additional Hyperliquid markets and independent strategy hypotheses. Each asset class and strategy passes the same research pipeline; no unreviewed simultaneous activation.

### Scope

- Additional crypto perpetuals (research/shadow first)
- HIP-3 equity, index, and commodity perpetuals on the same Hyperliquid platform
- Asset-specific metadata profiles (`CRYPTO_24_7`, `HIP3_EQUITY_PERP`, `HIP3_INDEX_PERP`, `HIP3_COMMODITY_PERP`)
- Independent strategy portfolio with correlation analysis

### Non-scope

- Parallel live activation
- Treating synthetic equity perps as real stock ownership
- Bypassing P5/P6 gates
- Runtime trading implementation in this planning phase

### Prerequisites

- P4 experiment pipeline
- P5 honest validation of Trend Strategy V1
- P6 paper soak learnings
- P2.5 dashboard production acceptance (operational monitoring)

### Sub-phases

#### P7A – Additional Crypto Perpetuals

- Additional liquid Hyperliquid crypto perpetuals
- Research and shadow mode first
- Not added solely to increase trade count
- Data history, liquidity, funding, and correlation reviewed

#### P7B – HIP-3 Equity Perpetuals

- Stock perpetuals via Hyperliquid/HIP-3 on the same platform
- **Not** real share ownership — synthetic perpetual exposure only
- Separate asset profile with liquidity, funding, gap, and corporate-action assumptions
- Research and shadow mode first

#### P7C – HIP-3 Index and Commodity Perpetuals

- Index and commodity perpetuals
- Separate asset profile
- Distinct market, oracle, funding, and liquidity rules
- Research and shadow mode first

#### P7D – Independent Strategy Portfolio

- Multiple economically distinct strategies (not merely more correlated assets)
- Separate risk budgets
- Correlation analysis and portfolio drawdown budget
- Evaluate marginal benefit vs single-strategy baseline

### Exit criteria

- [ ] Multi-asset metadata contract defined (planning issue)
- [ ] HIP-3 equity perpetual validation requirements documented
- [ ] Correlated multi-asset exposure model defined
- [ ] Each candidate has experiment chain through P5-equivalent gates
- [ ] Correlation to V1 measured
- [ ] At most one new candidate in paper at a time unless ADR approves

### Stop criteria

- High correlation cluster → reject diversification claim
- Asset profile gaps → block paper promotion for that market

### Risks

- Apparent diversification with correlated exposure (R-018, R-022)
- HIP-3 equity perps carry distinct funding/oracle/liquidity risks (R-023)
- Synthetic equity perps must not be described as real stock holdings (R-024)

**Architecture target:** See `docs/ARCHITECTURE.md` § Multi-asset target architecture and ADR-014.

**Current gap:** Planning issues only; no multi-asset runtime implementation.

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
