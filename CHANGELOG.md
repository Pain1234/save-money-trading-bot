# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added (P4.9 regime behaviour — #289)

- Deterministic behaviour labels + transition-risk profile under
  `services/research/regime_behaviour/` (`behavior_profile.json`).
- Policy `1.0` content-hashed; no LLM as label source; Sideways zero-trades →
  `DEFENSIVE_INACTIVE` (not failure). Runner + semantic repro updated.
- Docs: `docs/research/REGIME_BEHAVIOUR.md`.

### Added (P4.9 regime quality metrics — #287)

- Per-regime raw quality metrics under `services/research/regime_quality/`
  (`regime_metrics.json`: gross/net, costs, worst/strongest, portfolio/symbol views).
- Optional versioned quality summary (score policy `1.0`); never decision-binding;
  missing → `NOT_AVAILABLE`; zero-activity regimes are valid.
- Runner writes `regime_metrics.json`; docs `docs/research/REGIME_QUALITY.md`.

### Fixed (P4.9 regime quality integrity — #287 / PR #340)

- Trade attribution reconciles unlabeled/INSUFFICIENT exits (coverage +
  source/excluded PnL); incomplete coverage → `evidence_status=INCONCLUSIVE`.
- Max drawdown uses contiguous regime episodes (rebased), not cross-regime
  equity chaining.
- Dataset pins must match `regime_labels.json`; run-dir evaluation verifies
  checksums. Turnover uses `quantity` × `entry_fill_price`.
- Optional benchmark closes; downside/tail/subperiod stability metrics added.

### Added (P4.9 regime classifier — #285)

- Versioned deterministic regime + transition classifier under
  `services/research/regime/` (`classifier_version` `1.0` + content hash).
- Research runner writes sealed-in-checksums `regime_labels.json` per run;
  semantic double-run compare includes the artifact.
- Docs: `docs/research/REGIME_CLASSIFIER.md`; extends #199 without private
  P5 numbers; ARTIFACT_FORMAT / REGIME_SCORECARD / P5 regimes updated.
- Unit + runner tests: Bull/Bear/Sideways, transitions, no cross-month
  period look-ahead, ex-post day-label contract, calendar-gap non-adjacency,
  INSUFFICIENT, hash stability, seal tamper rejection, repro parity.

### Added (P7 architecture — centralized intent / single execution owner)

- ADR-018: centralized Strategy Intent allocation and a single execution owner
  per trading account (architecture/planning only — not runtime activation).
- ADR-014 amendment: research universe ≠ execution venue; orthogonal
  `asset_class` × `instrument_type` × venue axes; HIP-3 index/commodity as
  synthetic perpetuals (not futures); identity scaffolding exception for
  #128–#130 under golden-fixture economic parity and P5 freeze-window rules.
- R-025: multiple execution writers / ambiguous order ownership.
- ROADMAP / ARCHITECTURE / milestone audit sync for P7 planning contracts
  (#104, #106, #128–#130, #135, #139, #304, #305).
- Note: accidental re-seed duplicates #306–#332 from a 2026-07-18 governance
  `--apply` were closed the same day as duplicates of canonical issues. Root
  cause of the apply remains **unknown** (HEAD not recorded). Ruled out on
  current `main`: “closed seeds ignored” (script already uses `state=all` +
  skip). Leading hypothesis: outdated worktree/branch. Record
  `git rev-parse HEAD` before future authenticated applies.

### Added (P4.9 Regime Evidence Scorecard — governance)

- Epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295) and child
  issues [#284](https://github.com/Pain1234/save-money-trading-bot/issues/284)–[#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)
  for a layered regime-based strategy evidence scorecard inside milestone P4.
- Contract `docs/research/REGIME_SCORECARD.md`, ADR-019, risk register rows
  R-026–R-031; ROADMAP / ARCHITECTURE / research docs updated.
- Extends existing #247/#248/#249 surfaces; no second registry; no auto-promotion;
  no private Strategy V1 thresholds frozen in this change.

### Added (P4.9 regime classifier — #285)

- Versioned deterministic monthly regime + transition classifier package
  (`services/research/regime/`, `classifier_version` `1.0` with content hash).
  Research runs emit `regime_labels.json`.
- Trend axis aligned with #199 (±5%); public three-way vol buckets use versioned
  absolute thresholds (not private P5 partition-B median).
- Docs: `REGIME_CLASSIFIER.md`, `P5_BENCHMARKS_REGIMES.md` mapping; unit + runner
  repro tests.

### Fixed (Dashboard design ↔ paper API — #238 re-review)

- Kill Switch / Paused show „Nicht verfügbar“ when `runtime` is null (no false AUS/Nein).
- Scheduler / Incidents cards distinguish endpoint errors from empty success
  („Nicht verfügbar“ vs „0 in letzten 50 Events“).
- Realized PnL KPI accent follows decimal sign (negative → danger).
- Playwright scenarios: stale heartbeat, summary 503, section endpoint failures
  (incl. equity/positions), and empty equity/positions/fills.
- Postgres repository test: `open_only` includes OPEN+CLOSING, excludes CLOSED, cursor works.
- Docs: `ARCHITECTURE.md` / `design-system.md` no longer claim mock dashboard data
  (design-system scope: Dashboard UI / paper monitoring, not Mock-Dashboard).

### Added (Dashboard design ↔ paper API — #238)

- Reconnected the existing Save-Money-Bot design shell on `/dashboard` to the
  read-only paper monitoring API (summary-first KPIs; equity, open positions,
  fills, and status cards stream via Suspense).
- View-model layer under `src/lib/dashboard/` (formatters, mapping, constants,
  navigation). Production routes no longer use financial mock fixtures.
- `GET /api/v1/positions?open_only=true` (and optional `status=`) so the open
  positions table does not client-filter a mixed page of open/closed rows.
- Vitest unit tests for view-models; Playwright visual suite uses a deterministic
  Paper API stub + login; control panels are disabled with a read-only banner.

### Changed (Dashboard design ↔ paper API — #238)

- Position side displayed as LONG per V1 `PaperSide` contract (no quantity-sign
  inference). Fills table titled “Letzte Fills” (no invented R-multiples).
- Footer/Sidebar copy updated for read-only paper monitoring; navbar shows the
  real session user and Logout (fake theme/notification/profile actions removed).

### Changed (P5 execution — gate status)

- P5_EXECUTION_STATUS: snapshot recording #204/#205 blocked pending human freezes, Partition B data, and holdout sufficiency.

### Changed (P5 execution — #196 freeze evidence)

- Candidate freeze: regression evidence refreshed on main tip b51bde6 (113+3); code hashes updated; STALE cleared.

### Added (P5 execution — #205 decision process)

- ADR-017: forward holdout + private research store process (prep; no final decision).

### Added (P5 execution — #204 pre-OOS)

- Execution status checklist: hard stops before opening forward holdout (prep only).

### Added (P5 execution — #203 bootstrap)

- bootstrap.py: path net-PnL/drawdown quantiles; small-n samples fail closed (N/A).

### Added (P5 execution — #202 parameter stability)

- parameter_stability.py: symmetric neighborhood diagnostics around frozen V1 params.

### Added (P5 execution — #201 cost stress)

- cost_stress.py: pre-registered scenarios; base funding mirrors frozen Spec.

### Added (P5 execution — #200 walk-forward)

- walk_forward.py: chronological folds with completed-monthly candle warmup (not a 620-day proxy).

### Added (P5 execution — #199 benchmarks)

- Benchmarks/regimes contract: buy-and-hold net under Spec costs when cost_parity=true (metrics 1.2 / #208).

### Added (P5 execution — #198 protocol)

- Validation protocol + decision rules: combined_elevated on Accept checklist; measurable neighborhood fragility rule; metrics schema 1.2.

### Added (P5 execution — #197 partitions)

- Data-exposure audit: forward holdout lock; purge/label embargo separated from completed-monthly feature warmup.

### Added (P5 execution — #196 candidate freeze)

- Candidate freeze prep synced to metrics schema **1.2**; Phase A audit resynced (#206–#210 closed). Regression evidence marked stale until re-run on final merged main.

### Added (P5 execution — #181 public/private gate)

- Private research store contract and public leakage gates for P5 artifacts.

### Added (P5 planning — honest validation)

- `docs/research/p5/` planning pack: Phase A audit, data-exposure audit template, candidate freeze template, validation protocol, decision rules (`ACCEPT_FOR_P6` / `REJECT` / `INCONCLUSIVE`), public/private artifact classification, execution checklist.
- Roadmap P5 section updated for honest-validation purpose, dependency chain, and milestone DoD (no OOS opened; no strategy parameter changes).

### Fixed (P2.5 — Issue #121)

- Confirmed ~2.13 s FastAPI residual as cross-region placement: moved paper-trading-api from sfo to europe-west4-drams3a with measured before/after Layer C (docs/operations/dashboard-fastapi-residual-121.md). Residual p95 fell ~97% on wallet/summary/status; API left co-located with Postgres/Dashboard.
- Opt-in setup timing headers behind PAPER_API_PERF_BREAKDOWN for further residual attribution (no pooling change in this experiment).


### Added (governance — P2.5 and P7 roadmap)

- **P2.5** milestone `P2.5 – Dashboard Performance & Responsiveness` with performance budgets and exit criteria in `ROADMAP.md`.
- Nine P2.5 seed issues: performance baseline, instrumentation, redundant DB read removal, dashboard summary API, cache policy, loading states, SQL/index audit, regression tests, production dashboard acceptance.
- **P7** renamed to `Multi-Asset and Independent Strategy Candidates` with sub-phases P7A–P7D (crypto, HIP-3 equity, HIP-3 index/commodity, independent strategy portfolio).
- Three P7 planning seed issues: multi-asset metadata contract, HIP-3 equity perpetual validation requirements, correlated multi-asset exposure model.
- ADR-014 in `docs/DECISION_LOG.md` — one Hyperliquid multi-asset platform with asset-specific profiles.
- `docs/github-project-p25-p7-setup.md` — GitHub Project field setup for P2.5/P7 issues.
- Dashboard maturity levels in `docs/railway-paper-trading-dashboard-v1.md`.
- Multi-asset target architecture section in `docs/ARCHITECTURE.md`.
- Risk register entries R-019 through R-024 (dashboard performance and multi-asset planning risks).

### Changed (governance)

- `ROADMAP.md` — P3 status **Complete** with evidence; P2.5 phase added; P7 renamed and expanded.
- `docs/RISK_REGISTER.md` — R-018 updated for multi-asset correlation; R-019–R-024 added.
- `docs/PROJECT_OPERATING_SYSTEM.md` — Phase field includes P2.5; Workstream field added.
- `scripts/github_project_setup.py` — P2.5 milestone, renamed P7, 12 new seed issues, milestone title repair, decimal phase keys.

### Note

No runtime performance optimizations, multi-asset trading, HIP-3 implementation, or live-trading changes in this governance batch. Issue numbers for new seed issues assigned on first `github_project_setup.py --apply`.

### Added (P2.5 — dashboard performance)

- `scripts/measure_dashboard_api_baseline.py` and `docs/operations/dashboard-performance-baseline.md` — reproducible API latency baseline (Issue #95).
- `services/paper_trading/perf_observability.py` — request timing middleware with `total_ms`, `db_ms`, `query_count`, correlation IDs (Issue #96).
- `GET /api/v1/dashboard-summary` — overview aggregate endpoint; shared `_runtime_readiness_snapshot()` reduces redundant DB reads (Issues #97, #98).
- Cache-Control TTLs on read-only API routes and Next.js `REVALIDATE` fetch policy (Issue #99).
- `docs/operations/dashboard-sql-audit.md` — SQL/index audit checklist (Issue #101).
- `tests/perf/` — reporting-only latency regression checks (Issue #102).
- `docs/operations/dashboard-production-acceptance.md` — Railway acceptance checklist (Issue #103).

### Changed (P2.5)

- Dashboard overview uses `fetchDashboardSummary()` instead of parallel status/wallet fetches.
- `services/paper_trading/api_dependencies.py` — per-request SQLAlchemy query metrics for read-only API sessions.
- Issue #101 audit protocol expanded beyond the #117 checklist: layered A–D measurement harnesses, evidence-based index gate, Railway private-DNS measurement path, events `payload_json` analysis, and honest `NOT_MEASURED` placeholders (no invented p50/p95).

### Added (P2.5 — Issue #101 measurable audit)

- `scripts/measure_dashboard_layer_c_api.py` — FastAPI Layer C harness (`X-Perf-*` headers, events payload share).
- `scripts/measure_dashboard_ssr.py` — Next.js Layer B TTFB / HTML size harness.
- `scripts/audit_dashboard_sql_explain.py` — PostgreSQL Layer D `EXPLAIN (ANALYZE, BUFFERS)` first + cursor page.
- `tests/e2e/dashboard-layer-a-perf.spec.ts` — Browser Layer A cold/warm/soft timings to visible content.
- `X-Perf-Total-Ms` / `X-Perf-Db-Ms` / `X-Perf-Query-Count` / `X-Perf-Response-Bytes` response headers for audit scripts.
- Skeleton `data-testid="dashboard-skeleton"` for Layer A observation.

### Fixed (P2.5 — Issue #101 harness review)

- Layer A: heading timing no longer waits on skeleton timeout; LCP via `PerformanceObserver`; true cold contexts; Overview soft-nav starts from Status.
- Layer C: fail-closed `PARTIAL` when `X-Perf-*` headers missing; warm-up probes renamed (not cold).
- Layer D: cursor anchor = last row of first page; `pg_class.reltuples` before EXPLAIN; exact `COUNT(*)` only after; `SET TRANSACTION READ ONLY` + `SET LOCAL statement_timeout`.
- Layer B: reject login-redirect HTML without dashboard auth marker.
- Layer A cold wording: fresh authenticated context (login may warm assets; not zero-cache).

### Added (P3 — historical market data)

- `docs/market-data-contract.md` - canonical historical market data contract (Issue #76).
- `services/market_data/manifest.py`, `content_hash.py` - dataset manifest schema and SHA-256 hashing (#77).
- `tests/market_data/fixtures/example_dataset_manifest.json` - example manifest (#77).
- ADR-012 in `docs/DECISION_LOG.md` - P2 dependency decision for P3 (#11 waiver).
- Migration `010_market_data_datasets` - catalog tables (#79).
- `services/market_data/raw_store.py`, `dataset_catalog.py`, `postgres_catalog.py` (#79).
- `services/market_data/historical_import.py` - raw capture and deterministic import (#80).
- `services/market_data/dataset_quality.py` (#81), `quarantine.py` (#82).
- `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md` (#84).

### Changed

- ADR-013 in `docs/DECISION_LOG.md` - hybrid PostgreSQL + filesystem dataset storage (#78).
- `docs/ARCHITECTURE.md` - candle persistence and market-data state described accurately (in-memory today; advisory lock is paper-worker scope).
- `docs/P3_HISTORICAL_DATA_PLAN.md` - determinism contract requires immutable raw artifact; raw capture assigned to issue drafts 4/5.
- `ROADMAP.md` - cross-link to P3 planning document.

### Added (P2)

- `docs/operations/metrics.md` - critical operational metrics catalog (Issue #16).
- `docs/operations/idempotency-audit.md` - idempotency path inventory (Issue #13).
- `docs/runbooks/worker-restart.md` - worker restart runbook (Issue #14).
- `scripts/reconcile_accounting.py` - wallet reconciliation CLI (Issue #12).
- `tests/scripts/test_reconcile_accounting.py` - exit code and cleanup tests.
- P2 runbooks: deployment-verify, worker-safe-stop, kill-switch (Issue #15).
- Tabletop incident docs/incidents/INC-20260714-001-tabletop-duplicate-fill.md.
- `docs/runbooks/backup-restore.md` - backup/restore runbook; local restore drill with committed trade data (Issue #11).
- `scripts/seed_restore_drill_data.py` - committed trade lifecycle seed for restore drill.
- `scripts/restore_drill_snapshot.py` - row-count and wallet snapshot compare for restore drill.
- `tests/scripts/test_restore_drill_snapshot.py` - snapshot compare unit tests.

### Changed

- GitHub default branch migrated from `cursor/railway-paper-dashboard-v1` to `main`
  (Issue #64, commit `10000d3`). Rollback branch retained.
- Branch protection with required CI checks enabled on `main` (Issue #65).
- `.github/workflows/ci.yml` — CI push trigger includes `main`.
- `docs/default-branch-migration-plan.md`, `docs/branch-protection.md` — post-migration
  status.
- `docs/runbooks/reconciliation-daily.md` - weekly reconciliation procedure (Issue #12).
- docs/runbooks/README.md - runbook index; backup/restore linked (Issue #11).
- ROADMAP.md - P2 local backup/restore drill exit criterion; Railway non-prod drill open.
- docs/RISK_REGISTER.md - R-006/R-007 linked to P2 runbooks and audit.
- docs/RISK_REGISTER.md - R-009 local drill with committed data; Railway restore open.

### Note

Issue #15 bundles three runbooks; see docs/P2-PR-SPLIT.md.
P2 kill-switch runbook remains partial (production = Railway worker stop).
Issue #11: local restore drill with snapshot compare passed; Railway non-prod restore remains open.

## [baseline-paper-v1.0.1] — 2026-07-14

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
