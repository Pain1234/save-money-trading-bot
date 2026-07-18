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
| P2.5 | Dashboard Performance & Responsiveness | Planned (seed issues closed; exit criteria **not** met — do not treat as complete) | No |
| **P3** | Versioned Historical Market Data | **Complete** | No |
| P4 | Research Engine und Research Workspace V1 | **In flight** (Lab #242/#243; catalog #265; chart #266; #245 ownership via #247 stack; #249 Validation Studies pinned; #250 E2E on `feat/250-research-e2e`; #246 compare merged onto this branch for real E2E) | No |
| P5 | Honest Validation of Trend Strategy V1 | **Planning** (helpers #200–#203 ≠ execution; #251–#254 open; no OOS opened) | No |
| P6 | Paper Trading Soak | **Not started** (Epic #46; sub-issues #256–#262; clock not started) | No |
| P7 | Multi-Asset and Independent Strategy Candidates | Planning + architecture contracts (ADR-018); identity scaffolding #128–#130 exception; no runtime activation until P5/P6 | No |
| P8 | Separate Micro-Live System | Blocked (boundary #184 only; no live impl issues) | **Yes — explicit human approval** |
| P9 | Controlled Scaling | Blocked (boundary #185 only; detailed split after P8) | **Yes — explicit human approval** |

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
- **P4** milestone title: `P4 – Research Engine und Research Workspace V1`. Engine + read-only workspace (#240) on `main`. Strategy Lab + start merged via PR #243; #242 **reopened** until manual UI acceptance with a valid dataset catalog is documented. Catalog visibility #265 (PR #267) and price/trade chart #266 (PR #268) **delivered and closed** — both merged on `main`. Durable job ownership (#245) is on this stack via #247. Robustness #247 / gate evaluator #248 / validation studies #249 (pinned evidence snapshots) delivered on the `feat/249-validation-studies` stack. #250 E2E suite on `feat/250-research-e2e`. Compare (#246) is merged onto this branch for real compare E2E. Audit: `docs/project-management/MILESTONE_COVERAGE_AUDIT.md`. Governance sync: #244.
- **P5** planning/helpers (#197–#203, #181) ≠ actual Strategy V1 validation. Execution issues: #251–#254; study register #255; final OOS #204 still blocked. See `docs/research/p5/README.md`.
- **P6** soak **not started**. Epic #46 decomposed into #256–#262; private telemetry boundary #182.
- **P2.5** seed issues are closed but ROADMAP exit criteria remain open — status drift documented in the coverage audit; not marked complete.
- **P7** planning + architecture (ADR-014 amended, ADR-018); identity scaffolding
  #128–#130 may merge under parity/freeze rules; no multi-asset runtime activation
  until P5/P6. Further activation decomposition after gates.
- **P8/P9** blocked; only boundary issues (#184/#185). Detailed live/scaling split required before any activation — no wallet/order/signing work.
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

**GitHub milestone:** `P4 – Research Engine und Research Workspace V1`

### Goal

Standardized strategy interfaces, reproducible experiments, experiment registry,
benchmarks, cost model, unified result reports — **and** a dashboard Research
Workspace that reads those artifacts without introducing a second research system.

### Scope

- `services/backtester/`, `services/strategy_engine/`, `services/risk_engine/`
- `services/research/` (Spec, runner, registry, metrics, costs, benchmarks)
- Read-only Research API + Dashboard Research UI (overview / list / detail)
- Strategy Lab + async start (in-process V1; durable recovery is #245)
- `docs/EXPERIMENT_TEMPLATE.md`, experiment issues
- Cost and slippage assumptions documented per experiment

### Non-scope (this milestone still open)

- Cancel / Retry / Re-run lifecycle (**bewusst zurückgestellt**)
- Pflicht zu Celery/Redis (nur falls in #245 bewusst gewählt)
- New Experiment Postgres tables; second registry; live/paper order actions from Research
- Private P5 Strategy V1 economic results in the public repo

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

#### Research Workspace — read-only slice (#240) — **abgeschlossen**

- [x] Thin read API over ExperimentRegistry + run artifacts (`/api/v1/research/...`)
- [x] Monitor / Research navigation; routes under `/dashboard/research`
- [x] Overview, experiment list (search/filter), experiment detail (metadata, config, metrics, equity/drawdown)
- [x] Missing values as „Nicht verfügbar“ / controlled errors; no productive mock data
- [x] Path-traversal protection; unknown experiment → 404; no live-order access from Research

#### Research Workspace — Strategy Lab + start (#242 / PR #243)

- [x] Code on `main` (PR #243 merged): Lab route, write API, filesystem job store, in-process worker
- [ ] **Manuelle UI-Abnahme** mit gültigem Dataset-Katalog dokumentiert → #242 remains open until then (also covered by #250)

#### Research Workspace — Trend Strategy V1 catalog (#265)

- [x] Canonical strategy id `trend_v1` listed once (alias `trend_strategy_v1` resolvable, not duplicated in UI)
- [x] Routes `/dashboard/research/strategies` and `/dashboard/research/strategies/trend_v1`
- [x] Strategy Lab shows display name + frozen parameter help; new specs store canonical id

#### Research Workspace — Price & trade chart (#266)

- [x] Depends on #243 (merged) and stable canonical id (#265)
- [x] Experiment detail view „Kurs & Trades“ from verified `trades.json` + bound dataset candles
- [x] Fail-closed on integrity / dataset mismatch; equity/drawdown charts unchanged

#### Delivered (closed — merged on `main`)

- [x] [#265](https://github.com/Pain1234/save-money-trading-bot/issues/265) P4.6 Make Trend Strategy V1 visible and selectable in Research (PR #267)
- [x] [#266](https://github.com/Pain1234/save-money-trading-bot/issues/266) P4.7 Add price and trade chart to research experiment details (PR #268)

#### Research Workspace — E2E, reproducibility, UI acceptance (#250) — **in progress on `feat/250-research-e2e`**

Stacked on `main → #245 (via #247) → #247 → #248 → #249` plus `#246` compare for real compare E2E.

- [x] API E2E suite `tests/research/test_e2e_acceptance.py` (matrix in Issue #250) without `RESEARCH_ALLOW_DIRTY_GIT`.
- [x] CLI compatibility smoke `tests/research/test_cli_compat.py`.
- [x] Manual UI acceptance checklist documented (`docs/research/RESEARCH_WORKSPACE_ACCEPTANCE.md`).
- [ ] Human execution of the manual checklist + evidence row filled in.
- [ ] Playwright research smoke or accepted Playwright waiver (see acceptance doc).

#### Still open (linked issues — see `docs/project-management/p4-research-workspace-follow-ups.md`)

- [ ] [#245](https://github.com/Pain1234/save-money-trading-bot/issues/245) P4.6b Durable Research Job Execution und Restart Recovery — ownership contract on this stack via #247
- [ ] [#246](https://github.com/Pain1234/save-money-trading-bot/issues/246) P4.7a Experiment- und Strategie-Vergleich — on this branch for compare E2E
- [ ] [#247](https://github.com/Pain1234/save-money-trading-bot/issues/247) P4.7b Robustness-Orchestrierung — code complete on this stack; issue/PR still open (not yet on `main`)
- [ ] [#248](https://github.com/Pain1234/save-money-trading-bot/issues/248) P4.7c Versionierter Gate Evaluator und Gate-Persistenz — code complete on this stack; issue/PR still open (not yet on `main`)
- [ ] [#249](https://github.com/Pain1234/save-money-trading-bot/issues/249) P4.7d Validation Studies API und UI — pinned evidence snapshots on this stack; issue/PR still open (not yet on `main`)
- [ ] [#250](https://github.com/Pain1234/save-money-trading-bot/issues/250) P4.8 Research E2E, Reproduzierbarkeit und UI-Abnahme — this PR; awaits review/merge and the human manual-checklist run
- [ ] Cancel / Retry / Re-run (explicitly deferred — no issue)

### Binding dependency chain

```
P3 → #141 → #142 → {#144, #49, #148} → #143 → {#48, #145} → #146 → #147 → engine done
→ #240 read-only → #242 Lab/start (Abnahme offen) → #265 catalog (delivered) → #266 chart (delivered)
→ #245 → {#246…#249} → #250 → P4 done → P5
```

Docs preparation may run in parallel from #142.

### Exit criteria

- [x] Every experiment traceable to commit + dataset version + config
- [x] Acceptance/rejection criteria applied consistently (process/DoD; enforced via issue/PR template — ongoing discipline)
- [x] Old results immutable; invalidation via registry and/or append-only sidecar only (`invalidated` status, reason, provenance, replacement run; original RunManifest unchanged)
- [x] P5 gates (OOS / walk-forward / cost-stress robustness) not pre-empted
- [x] Research Workspace usable for browsing real experiments (API + UI) without a parallel system
- [x] Strategy visible/selectable without prior runs (#265); trade chart on completed runs (#266)
- [ ] Lab usable; Lab UI-Abnahme + durable jobs / compare / robustness / gates / validation studies / E2E delivered or explicitly deferred with issues

### Stop criteria

- Overfitting detected without OOS discipline → halt new strategy promotion

### Risks

- Backtest bias; cost model optimism; UI inventing metrics not produced by the engine

**Current gap:** Engine + read-only workspace + Lab code on `main`. Strategy catalog (#265) and price/trade chart (#266) **delivered** (PR #267/#268). #250 E2E suite on `feat/250-research-e2e` (stacked on #245-via-#247 / #247 / #248 / #249, plus #246 for compare E2E); human manual UI checklist + Playwright waiver/smoke still outstanding. #242 stays open until that manual run is recorded. **P4 not complete.** P5 economic execution remains gated on usable workspace + P5 execution chain.

---

## P5 – Honest Validation of Trend Strategy V1

**GitHub milestone:** `P5 – Honest Validation of Trend Strategy V1`

### Goal

Honestly decide whether frozen Strategy V1 warrants promotion evidence for P6 — not prove profitability. Allowed outcomes only: `ACCEPT_FOR_P6`, `REJECT`, `INCONCLUSIVE` (`INCONCLUSIVE` is not promotion). Planning and gates: [`docs/research/p5/`](docs/research/p5/README.md).

### Scope

- Research only; **no strategy parameter changes** under Strategy V1 without new version + new freeze
- Data-exposure audit, candidate freeze, pre-registered protocol, walk-forward, cost stress, parameter stability, bootstrap/Monte Carlo, one-shot untouched OOS
- Results stored as **private-edge** experiment artifacts (#181); public repo keeps methodology/templates only
- Generic Validation Study **infrastructure** is P4.7d (#249); Strategy V1 study registration is [#255](https://github.com/Pain1234/save-money-trading-bot/issues/255) (metadata/status only)

### Non-scope

- New strategies; new assets / HYPE / HIP-3; paper soak (P6); live trading; optimizing thresholds after seeing OOS
- Treating closed #200–#203 as proof that V1 was validated

### Prerequisites

- P4 research engine + usable Research Workspace (read API + browse UI at minimum; Lab/async as needed for P5 workflow)
- #181 public/private separation complete before first real P5 result
- Signed candidate freeze + validation protocol **before** opening final holdout
- **Actual** robustness executions (#251–#254) + human review before #204

### Binding issue chain

```text
#181 → #196 → #197 → #198 → #199 → {#200–#203 Planung/Helfer}
  → {#251–#254 P5-04E–P5-07E Ausführung} → human pre-OOS → #204 → #205
```

Canonical risk: [#47](https://github.com/Pain1234/save-money-trading-bot/issues/47). Canonical boundary: [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181).

| Planung/Helfer | Tatsächliche Ausführung |
|----------------|-------------------------|
| #200 Walk-forward plan | [#251](https://github.com/Pain1234/save-money-trading-bot/issues/251) P5-04E |
| #201 Cost stress plan | [#252](https://github.com/Pain1234/save-money-trading-bot/issues/252) P5-05E |
| #202 Parameter stability plan | [#253](https://github.com/Pain1234/save-money-trading-bot/issues/253) P5-06E |
| #203 Bootstrap/MC plan | [#254](https://github.com/Pain1234/save-money-trading-bot/issues/254) P5-07E |
| P4.7d Validation Studies infra | [#255](https://github.com/Pain1234/save-money-trading-bot/issues/255) P5-10 register (no metrics) |

### Deliverables

- Planning pack under `docs/research/p5/` (templates; no simulated results)
- Frozen holdout + one-shot OOS report (private) — **not opened in this governance sync**
- Walk-forward, cost-stress, stability, uncertainty reports (private) via #251–#254
- Documented `ACCEPT_FOR_P6` / `REJECT` / `INCONCLUSIVE` in decision log (#205)

### Exit criteria

- [ ] Strategy V1 uniquely frozen; exposure audited; protocol frozen before OOS view
- [ ] Benchmarks + sample-sufficiency + decision rules pre-registered
- [ ] Walk-forward, cost stress, parameter stability **executed** (#251–#253); bootstrap/MC **executed** or methodically N/A (#254)
- [ ] Final OOS evaluated exactly once (#204); no post-hoc parameter fishing; no leakage
- [ ] Outcome documented; human sign-off in decision log; #47 closed; #181 satisfied
- [ ] No new strategy/assets; no P6/P8 pre-emption; no live-trading code

Full checklist: `docs/research/p5/P5_EXECUTION_CHECKLIST.md`.

### Stop criteria

- Leakage, unclear dataset, freeze violation, unreproducible results, missing costs, public leak of private results, critical P4 defect, or retuning after failed OOS → halt; no promotion; human decision

### Risks

- Strategy overfitting; regime change; false OOS claims; public/private leakage

**Current gap:** Planning/helpers largely present; **no** actual #251–#254 execution; **no** final holdout opened; **no** formal V1 OOS decision.

---

## P6 – Paper Trading Soak

**GitHub milestone:** `P6 – Paper Trading Soak`

### Goal

≥ 90 days stable paper operation with daily reconciliation, funding/mark price observation, paper-to-live decay measurement, documented operational incidents.

### Scope

- Railway paper stack (`bot.save-money.xyz` dashboard, worker, API, Postgres)
- Monitoring and incident logging
- Decomposed implementation under Epic [#46](https://github.com/Pain1234/save-money-trading-bot/issues/46):
  - [#256](https://github.com/Pain1234/save-money-trading-bot/issues/256) P6-00 Soak Entry Gate und Configuration Freeze
  - [#257](https://github.com/Pain1234/save-money-trading-bot/issues/257) P6-01 Soak Telemetry und Daily Snapshot
  - [#258](https://github.com/Pain1234/save-money-trading-bot/issues/258) P6-02 Reconciliation Archive
  - [#259](https://github.com/Pain1234/save-money-trading-bot/issues/259) P6-03 Incident und Abort Handling
  - [#260](https://github.com/Pain1234/save-money-trading-bot/issues/260) P6-04 Execution-Decay Analysis
  - [#261](https://github.com/Pain1234/save-money-trading-bot/issues/261) P6-05 Soak Progress UI
  - [#262](https://github.com/Pain1234/save-money-trading-bot/issues/262) P6-06 Final P6 Decision
- Private telemetry boundary: [#182](https://github.com/Pain1234/save-money-trading-bot/issues/182)

### Non-scope

- Real orders; capital at risk
- Treating #46 as a single mega-implementation PR

### Prerequisites

- P5 accept decision (or explicit waiver documented)
- P2 operational minimum

### Deliverables

- Soak log (daily reconciliation, heartbeat, readiness)
- Decay metrics vs backtest (private)
- Incident register entries
- Final human decision (#262) — **no** automatic P8 activation

### Exit criteria

- [ ] 90 consecutive days without unresolved S1
- [ ] Daily reconciliation completed and archived
- [ ] Paper-to-live decay documented with assumptions
- [ ] #256–#262 complete or explicitly waived; #46 epic checklist done

### Stop criteria

- S1 during soak → pause promotion clock until root cause closed

### Risks

- Paper fill model ≠ live fills; funding/slippage drift

**Current gap:** Deployment may be in progress; **90-day soak not started**; sub-issues filed, not implemented.

---

## P7 – Multi-Asset and Independent Strategy Candidates

**GitHub milestone:** `P7 – Multi-Asset and Independent Strategy Candidates`

**Planning and architecture contracts only** for multi-asset / multi-strategy
**activation**. Productive implementation and market activation remain blocked
until P4 completion, P5 honest validation, P6 paper soak, and required human
approvals (ADR-014 / ADR-018).

**Identity scaffolding exception:** #128–#130 (InstrumentId + additive plumbing)
MAY merge before P5/P6 as cross-cutting architectural scaffolding only, under
ADR-018 parity and freeze-window rules. Scaffolding ≠ runtime activation.

### Goal

Expand research beyond BTC/ETH/SOL toward multiple research universes, asset
classes, timeframes, and economically independent strategy modules — with
centralized opportunity selection, portfolio allocation, internal strategy
sleeves, and exactly one order owner per trading account. No uncoordinated bots
with direct write access to the same account (ADR-018, R-025).

### Scope

- Architecture / governance / planning issues (contracts, ADRs, issue map)
- Research universe ≠ execution venue
- Orthogonal metadata: `asset_class` × `instrument_type` × venue profile (#104)
- Correlated exposure / cluster risk model (#106)
- Instrument identity scaffolding (#128–#130) under parity gates
- Independent / portfolio shadow trading plan (#135) — sleeves, netting,
  allocation, single executor
- Multi-asset research dashboard plan (#139) — distinct from P4.9 UI
- Multi-timeframe role contract and normalized portfolio StrategyIntent contract
  (planning issues)
- Additional crypto perpetuals and HIP-3 synthetic perpetuals as **future**
  research/shadow candidates (P7A–C) — not activated in this planning work
- Independent strategy portfolio hypotheses (P7D) — planning only

### Non-scope

- Parallel live activation; wallet signing; real exchange orders
- Treating synthetic equity/index/commodity perps as real ownership or as futures
- Bypassing P5/P6 gates for multi-asset / multi-strategy **activation**
- Runtime trading implementation of allocator, ranking, clustering, or
  multi-writer execution in this planning phase
- Hyperliquid subaccounts / multi-process live isolation (P8 — #184)
- Duplicating P4.9 Research Workspace UI (#297–#303)

### Prerequisites

- P4 experiment pipeline / workspace contracts
- P5 honest validation of Trend Strategy V1
- P6 paper soak learnings
- P2.5 dashboard production acceptance (operational monitoring)
- Before P5 candidate freeze: #128–#130 merged+parity **or** explicitly deferred
  until after P6 (ADR-018)

### Sub-phases

#### P7A – Additional Crypto Perpetuals

- Additional liquid Hyperliquid crypto perpetuals
- Research and shadow mode first
- Not added solely to increase trade count
- Data history, liquidity, funding, and correlation reviewed

#### P7B – HIP-3 Equity Perpetuals

- Stock perpetuals via Hyperliquid/HIP-3 on the same platform
- **Not** real share ownership — `EQUITY` + `SYNTHETIC_PERPETUAL` only
- Separate asset profile with liquidity, funding, gap, and corporate-action assumptions
- Research and shadow mode first

#### P7C – HIP-3 Index and Commodity Perpetuals

- Index and commodity **synthetic perpetuals** (not futures)
- Separate asset profile (`INDEX`/`COMMODITY` + `SYNTHETIC_PERPETUAL`)
- Distinct market, oracle, funding, and liquidity rules
- Research and shadow mode first

#### P7D – Independent Strategy Portfolio

- Multiple economically distinct strategies (not merely more correlated assets)
- Strategy sleeves, central allocation, single execution owner (ADR-018)
- Correlation analysis and portfolio drawdown budget (#106)
- Evaluate marginal benefit vs single-strategy baseline

### Exit criteria

- [ ] Multi-asset metadata contract defined (planning issue #104)
- [ ] HIP-3 equity perpetual validation requirements documented (#105)
- [ ] Correlated multi-asset exposure model defined (#106)
- [ ] Instrument identity scaffolding merged or explicitly deferred (#128–#130)
- [ ] Centralized intent / single execution owner architecture accepted (ADR-018)
- [ ] Each candidate has experiment chain through P5-equivalent gates
- [ ] Correlation to V1 measured
- [ ] At most one new candidate in paper at a time unless ADR approves

### Stop criteria

- High correlation cluster → reject diversification claim
- Asset profile gaps → block paper promotion for that market
- More than one active order writer per account, or order not traceable to
  exactly one allocation decision → halt multi-strategy execution design (R-025)

### Risks

- Apparent diversification with correlated exposure (R-018, R-022)
- HIP-3 equity perps carry distinct funding/oracle/liquidity risks (R-023)
- Synthetic equity perps must not be described as real stock holdings (R-024)
- Multiple execution writers / ambiguous order ownership (R-025)

**Architecture target:** See `docs/ARCHITECTURE.md` § Multi-asset target
architecture, ADR-014 (amended), and ADR-018.

**Current gap:** Planning/architecture issues
(`#104`–`#106`, `#128`–`#130`, `#134`–`#135`, `#139`, `#183`, `#304`
MTF-role contract, `#305` StrategyIntent contract; ADR-018). No multi-asset /
multi-strategy **runtime** implementation. Identity scaffolding may proceed
under ADR-018; further activation decomposition **after** P5/P6 gates.

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
- Starting live implementation issues, wallet signing, or real order logic in this sync
- Detailed decomposition is **required before activation** and is not started here (boundary only: [#184](https://github.com/Pain1234/save-money-trading-bot/issues/184))

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

**Current gap:** Live execution explicitly not implemented; milestone **blockiert**.

---

## P9 – Controlled Scaling

**GitHub milestone:** `P9 – Controlled Scaling`

**Blocked until explicit human approval after P8.**

### Goal

Scale only on real evidence: capital limits, drawdown limits, correlation budget, documented downgrade rules, economic viability proof.

### Prerequisites

- P8 micro-live evidence; **human approval**

### Non-scope (this sync)

- No scaling implementation issues; detailed split only after P8 (boundary: [#185](https://github.com/Pain1234/save-money-trading-bot/issues/185))

### Exit criteria

- [ ] Scaling rules in risk spec enforced in code
- [ ] Drawdown breach triggers automatic downgrade
- [ ] Documented economic review

**Current gap:** Not applicable until P8; milestone **blockiert**.

---

## How to use this roadmap

1. Pick the **active phase** milestone in GitHub.
2. Create or select an **issue** with scope, non-scope, and acceptance criteria.
3. One branch / one PR per issue (`docs/PROJECT_OPERATING_SYSTEM.md`).
4. Update this file only when phase status changes with evidence (link PR/issue).
5. Coverage audit: [`docs/project-management/MILESTONE_COVERAGE_AUDIT.md`](docs/project-management/MILESTONE_COVERAGE_AUDIT.md).