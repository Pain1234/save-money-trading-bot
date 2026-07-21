# Data, Strategy and Research Audit — Auditor A

**Issue:** [#371](https://github.com/Pain1234/save-money-trading-bot/issues/371)

**Audit branch:** `audit/full-system-behavior-verification`

**Immutable audit SHA:** `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`

**Audit date:** 2026-07-19 (Europe/Berlin)

**Scope:** Market Data, Dataset Manifests, candle integrity/aggregation, current instrument identity, Strategy V1, research/backtest/paper parity, Research Registry/Gates/Scorecards/provenance/invalidation/raw artifacts, P4/P5 boundary, Research API/UI identity binding.

**Auditor-A phase recommendation:** `BLOCK_P5` until all P1 findings below are resolved and affected evidence is re-qualified. This is an Auditor-A scope recommendation, not the combined system-audit verdict.

## 1. Evidence rules and boundaries

This report distinguishes:

- **Soll:** binding repository contract at the audit SHA.
- **Code:** executable implementation inspected at the audit SHA.
- **Test:** commands actually executed in this worktree during this audit.
- **Runtime:** deployed or persistent behavior directly observed during this audit.
- **Not checked:** explicitly outside the available, safe evidence.

No strategy/risk parameter, market, P5 holdout, P5 execution, live endpoint, wallet, production configuration, production data, existing research artifact, or finding issue was changed. Synthetic negative tests used only process memory or temporary directories. No private P5 metric/value was accessed or reported.

The worktree contained unrelated changes to `docs/product-specification.md`, `docs/risk-specification.md`, and `docs/strategy-specification.md` when this auditor started. Findings against the Strategy contract were rechecked against `git show HEAD:docs/strategy-specification.md`; they are present at the immutable audit SHA and are not based on those unrelated line-ending changes.

### Source-of-truth material reviewed

Fully read for this scope: `AGENTS.md`, `ROADMAP.md`, GitHub Issue #371, `docs/ARCHITECTURE.md`, `docs/PROJECT_OPERATING_SYSTEM.md`, `docs/strategy-specification.md`, `docs/strategy-v1-parameter-inventory.md`, `docs/paper-trading-orchestrator-v1.md`, `docs/RISK_REGISTER.md`, `docs/market-data-contract.md`, `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md`, `docs/research/README.md`, `EXPERIMENT_SPEC.md`, `IDENTITY.md`, `ARTIFACT_FORMAT.md`, `REPRODUCIBILITY.md`, `INVALIDATION.md`, `GATES.md`, `SCORECARDS.md`, `REGIME_SCORECARD.md`, `VALIDATION_STUDIES.md`, `BACKTESTER_PAPER_PARITY.md`, `P4_ACCEPTANCE.md`, `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md`, public P5 README/status/pre-OOS/public-private-artifact contracts, and the Market Data/Strategy/Backtester/Paper area READMEs. Relevant implementations and tests under `services/{market_data,strategy_engine,backtester,research,paper_trading}` and `tests/{market_data,strategy_engine,backtester,research,paper_trading,dashboard}` were traced.

## 2. Decision table

Status vocabulary is restricted to Issue #371 values.

| Contract / invariant | Status | Soll evidence | Code evidence | Test evidence | Runtime / limit |
|---|---|---|---|---|---|
| Deterministic DatasetManifest ID/content hash | `PARTIALLY_VERIFIED` | `docs/market-data-contract.md:86-102`; `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md:7-29` | `services/market_data/content_hash.py:48-89`; `services/market_data/manifest.py:19-75` | Market Data suite: 172 passed | Real catalog provenance not observed; raw-ID mismatch path contradicts end-to-end trust (A-FINDING-05). |
| Candle OHLCV, gaps, duplicates, stale and quarantine | `VERIFIED` | `docs/market-data-contract.md:24-65`; `services/market_data/README.md` | `services/market_data/dataset_quality.py:31-130`; `services/market_data/quarantine.py:31-113` | 172 Market Data tests passed, including negative integrity paths | No deployed catalog queried. |
| Closed-candle/look-ahead boundary | `VERIFIED` | `docs/strategy-specification.md:38-52`; `docs/market-data-contract.md:42-47` | `services/market_data/timeframes.py:88-89`; `services/market_data/closed.py:18-27`; `services/backtester/data.py:10-30` | Market Data + Strategy/Backtest parity suites green | Deployed feed not observed. |
| Weekly/monthly aggregation correctness in isolation | `VERIFIED` | `docs/market-data-contract.md:73-79` | `services/market_data/aggregation.py:21-145`; research export derives both at `services/research/hl_dataset_export.py:300-315` | Market Data suite green; conflicting-native negative test detects conflict when merge is enabled | Paper production-style path disables the merge check (A-FINDING-03). |
| Current symbol/instrument identity | `PARTIALLY_VERIFIED` | V1 is BTC/ETH/SOL; generalized `InstrumentId` is target-state planning, not required current runtime | `services/market_data/models.py:13-16`; unknown provider symbols fail at `services/market_data/symbols.py:30-46`; no `InstrumentId` implementation found | Symbol mapping/constraint tests are included in green suites | Cross-venue/instrument identity is not implemented and was not treated as active V1. |
| Frozen Strategy V1 parameter defaults | `VERIFIED` | `docs/strategy-v1-parameter-inventory.md`; freeze table at `docs/strategy-specification.md:510-532` | `services/strategy_engine/constants.py:8-24`; `services/strategy_engine/models.py:115-131` | 144 Strategy/Backtest/parity tests passed | Research accepts undeclared keys while silently ignoring them (separate identity failure, A-FINDING-02). |
| Frozen Strategy V1 Monthly-Regime exit | `CONTRADICTED` | Required at `docs/strategy-specification.md:60`, `:331`, `:358-364` | Reason code exists only at `services/strategy_engine/models.py:44`; executable intent enum at `:67-72` has no exit; Backtester and Paper consume only `LONG_ENTRY` at `services/backtester/engine.py:563-599` and `services/paper_trading/evaluation.py:139-147` | Executable enum probe has no exit kind; no matching implementation/test found | Deployed behavior not tested; code contradiction is sufficient for A-FINDING-01. |
| Backtester ↔ Paper signal/lifecycle parity | `PARTIALLY_VERIFIED` | `docs/research/BACKTESTER_PAPER_PARITY.md:1-23` | Both call `StrategyEngine.evaluate`: `services/backtester/engine.py:548-560`, `services/paper_trading/evaluation.py:82-88` | 144 tests passed, including `test_backtester_parity.py` and `test_backtester_signal_parity.py` | Tests use identical synthetic inputs; production Paper higher-timeframe input provenance differs (A-FINDING-03). Both paths also share the missing spec exit (A-FINDING-01). |
| Experiment identity binds effective Strategy parameters | `CONTRADICTED` | `docs/research/EXPERIMENT_SPEC.md:9-25`; resolver promises unknown keys fail | Raw parameters enter semantic ID at `services/research/experiment_spec.py:127-159` and `services/research/identity.py:29-52`, but `StrategyParameters` lacks `extra="forbid"` at `services/strategy_engine/models.py:115-131`; resolver calls it at `services/research/strategy_resolver.py:160-167` | Negative probe accepted `misspelled_parameter` and executed default value | No real public run inspected; A-FINDING-02 blocks identity claims. |
| Run artifact sealing and checksum trust anchor | `VERIFIED` for synthetic fixtures | `docs/research/ARTIFACT_FORMAT.md:1-47` | `services/research/artifacts.py:17-129`; `services/research/registry.py:53-138` | Registry/repro/gate/scorecard/artifact suites green | No real public or private artifact tree was read. |
| Experiment invalidation remains fail-closed | `CONTRADICTED` | `docs/research/INVALIDATION.md:1-16` | Sidecar is written at `services/research/registry.py:142-187`, but `show()` trusts the latest JSONL line only at `:133-138`; reconstruction emits complete from immutable RunManifest at `:240-288` | Temp negative test: status changed `invalidated → complete` while sidecar still existed | A-FINDING-04; no existing artifact mutated. |
| Gates/Scorecards use pinned sealed evidence and no auto-promotion | `VERIFIED` for synthetic fixtures | `docs/research/GATES.md`; `docs/research/SCORECARDS.md` | Gate re-verification at `services/research/gate_evaluator.py:941-1001`; Scorecard re-verification at `services/research/scorecard_evaluator.py:494-595` | 73 gate tests + 53 scorecard/artifact tests passed; one scorecard test skipped | Real public/private evidence graph not available. Experiment invalidation weakness can undermine upstream status until fixed. |
| Research API/UI binds experiment/run/scorecard identity and fail-closed states | `VERIFIED` for tested surfaces | `docs/research/SCORECARDS.md`, `VALIDATION_STUDIES.md` | API carries both IDs (`services/research/api.py:108-191`); UI binds scorecards by run and study pins (`src/lib/research/scorecard-binding.ts:282-323`, `:399-442`) | 57 validation/read-API tests + 44 focused UI tests passed | Browser/deployed UI not observed. |
| Raw artifact ↔ `raw_dataset_id` ↔ manifest provenance | `CONTRADICTED` | `docs/market-data-contract.md:49-65`, `:86-102` | In-memory catalog checks same-ID hash at `services/market_data/dataset_catalog.py:64-70`; PostgreSQL silently ignores same-ID conflict at `services/market_data/postgres_catalog.py:24-48`, and publish does not compare `manifest.raw_content_hash` to raw row at `:50-79` | Existing Postgres tests do not cover duplicate raw-ID/different-content; 3 passed before teardown error | A-FINDING-05; production catalog not queried. |
| P4/P5 boundary and holdout protection | `PARTIALLY_VERIFIED` | Public status says holdout `NO`/`SEALED` at `docs/research/p5/P5_EXECUTION_STATUS.md:4`, `:70-72` and calendar/human gates remain unmet | No code path was used to open or execute P5 | No P5 test/run invoked | Private store and actual holdout ACL/state were intentionally not accessed: `NOT_VERIFIABLE` beyond public metadata. |
| Architecture document reflects current P3 implementation | `DOCUMENTATION_DRIFT` | ROADMAP declares P3 complete at `ROADMAP.md:38`, `:353` | Durable catalog/raw implementations and migrations 010/011 exist | Market Data tests green | `docs/ARCHITECTURE.md:96`, `:121-122` still says no durable catalog/candles and migrations only 001-009 (A-FINDING-06). |

## 3. Data and manifest audit

### Soll

The canonical contract requires immutable raw provider payloads, validated normalized candles, complete weekly/monthly aggregates derived from daily data, deterministic dataset identity, parent links for derived layers, and quarantine of invalid/disconnected data (`docs/market-data-contract.md:15-20`, `:49-79`, `:86-102`). Closed-candle eligibility is `close_time <= evaluation_time` (`docs/market-data-contract.md:42-47`).

### Code

- Canonical candle hash covers symbol, timeframe, timestamps, OHLCV and `is_closed`, sorted by identity (`services/market_data/content_hash.py:48-74`). Dataset ID binds schema, source and content hash (`:86-89`).
- Aggregation rejects incomplete or still-open buckets (`services/market_data/aggregation.py:21-58`) and implements ISO Monday-Sunday weekly plus complete calendar monthly (`:76-145`).
- Series quality detects malformed candles, conflicts, gaps and staleness (`services/market_data/dataset_quality.py:31-90`); quarantine blocks `INVALID`/`DISCONNECTED` and requires an explicit warning allowance for `INCOMPLETE`/`STALE` (`services/market_data/quarantine.py:31-69`).
- Public research export starts from daily provider pages and derives both weekly and monthly (`services/research/hl_dataset_export.py:300-315`), validates all three timeframes (`:349-382`), and hashes the combined bundle into the manifest (`:385-429`).
- The filesystem raw store is content addressed and re-hashes on load (`services/market_data/raw_store.py:26-70`). The PostgreSQL catalog has the raw-ID fail-open mismatch in A-FINDING-05.

### Test

`python -m pytest tests/market_data -m "not live and not postgres and not soak" -q` completed in 8.18 s (wrapper 9.34 s): **172 passed, 7 deselected**. Positive and negative coverage includes aggregation, native/aggregate conflict, gaps, quarantine, look-ahead, deterministic import/manifests, raw store, and symbols.

The production-style in-memory negative probe constructed a structurally valid native monthly candle that differed from the complete daily aggregate. With `aggregate_higher_timeframes=False`, status was `VALID`, the differing native close was consumed, and `MD_DUPLICATE_CONFLICT=False`. Re-running the same repository with merging enabled produced `INVALID` and `MD_DUPLICATE_CONFLICT=True`. This is A-FINDING-03.

### Runtime / not checked

No deployed Market Data runtime, production database, real provider request, or real public catalog was queried. The only PostgreSQL test attempt used the configured local test fixture: three tests passed, then fixture teardown failed (details in §8). No further DB suite, downgrade, repair, or mutation was attempted.

## 4. Strategy V1 and parity audit

### Soll

Frozen defaults and warmup minima are explicit in `docs/strategy-v1-parameter-inventory.md` and `docs/strategy-specification.md:510-532`. The frozen exit contract requires Monthly-Regime false to emit `RC_EXIT_REGIME_MONTHLY` at the monthly event and execute at the next daily close (`docs/strategy-specification.md:358-364`). Weekly trend break is intentionally entry-only (`:371-384`).

### Code

Entry filters, default parameters, stop math and candle validation are centralized in `strategy_engine`; Backtester and Paper both call this same engine. That is strong positive parity for the behavior the engine actually implements.

The Strategy output vocabulary, however, contains only `LONG_ENTRY`, `NO_ENTRY`, `INVALID_DATA`, and `INSUFFICIENT_HISTORY` (`services/strategy_engine/models.py:67-72`). `RC_EXIT_REGIME_MONTHLY` is declared (`:44`) but is never referenced elsewhere under `services/` or `tests/`. Backtester only queues a pending intent for `LONG_ENTRY` (`services/backtester/engine.py:563-599`); Paper only creates an intent for `LONG_ENTRY` (`services/paper_trading/evaluation.py:139-147`). Therefore shared-engine parity does not prove spec parity: both paths omit the same required exit.

Production Paper input construction explicitly sets `aggregate_higher_timeframes=False` (`services/paper_trading/scheduler_context.py:74-89`). Market Data then returns native higher-timeframe rows without aggregate comparison (`services/market_data/bundle.py:93-116`). By contrast, the public research export derives monthly from daily (`services/research/hl_dataset_export.py:300-315`). This leaves a source-level parity gap even though identical-bundle signal tests pass.

### Test

`python -m pytest tests/strategy_engine tests/backtester tests/paper_trading/test_backtester_parity.py tests/paper_trading/test_backtester_signal_parity.py -m "not live and not postgres and not soak" -q` completed in 0.58 s (wrapper 1.731 s): **144 passed**.

The executable enum probe returned:

```text
SIGNAL_INTENT_KINDS=LONG_ENTRY,NO_ENTRY,INVALID_DATA,INSUFFICIENT_HISTORY
MONTHLY_EXIT_REASON_PRESENT=RC_EXIT_REGIME_MONTHLY
```

This is a negative contract result, not a passing exit test.

### Runtime / not checked

No deployed Paper worker or persistent positions were exercised. Paper fill, risk and accounting internals beyond the shared Strategy input/output boundary belong to Auditor B.

## 5. Research provenance, registry, gates and scorecards

### Soll

Experiment identity must bind the full effective configuration; complete run artifacts are sealed; invalidation is append-only and must not mutate the RunManifest; gates and scorecards must read only pinned, sealed evidence; invalidated/missing/legacy evidence must fail closed; promotion remains human-owned (`docs/research/IDENTITY.md`, `ARTIFACT_FORMAT.md`, `INVALIDATION.md`, `GATES.md`, `SCORECARDS.md`).

### Code and test

Positive results:

- Experiment/run IDs hash the semantic ExperimentSpec plus code/dataset/model/environment pins (`services/research/identity.py:29-93`).
- Runner requires a clean, resolvable Git commit by default and rechecks before sealing (`services/research/runner.py:314-381` and its finalization guard).
- Registry trust-anchor checksums are verified against the finalized directory (`services/research/registry.py:53-80`, `:122-138`).
- Gate and scorecard policies, artifact checksums, robustness seals and invalidations have substantial negative coverage; focused suites passed (§8).
- Research API/UI focused tests correctly preserve experiment/run identity and present legacy, invalidated and missing evidence without inventing values.

Contradictions:

- `ExperimentSpec.parameters` is untyped free-form data (`services/research/experiment_spec.py:135`), and it participates in experiment/run identity. Resolver documentation says unknown keys fail (`services/research/strategy_resolver.py:160-167`), but `StrategyParameters` is only frozen, not `extra="forbid"` (`services/strategy_engine/models.py:115-131`). The negative probe accepted a misspelled key while executing the default value (A-FINDING-02).
- Experiment invalidation writes a sidecar but lookup never consults it (`services/research/registry.py:133-187`). A later complete JSONL row reactivated the run while the invalidation sidecar remained. Reconstruction similarly infers `complete` from the immutable RunManifest without sidecar binding (`:240-288`) (A-FINDING-04).

### Runtime / not checked

No real public run registry is committed. No private P5 registry/artifact was accessed. Consequently, real run/gate/scorecard/study provenance is `NOT_VERIFIABLE` in this audit; only implementation plus public synthetic tests were verified.

## 6. Public provenance chain (no private identifiers)

Only committed, public-core identifiers are reported:

```text
public local-lab raw_dataset_id
  raw-3d9279e1ff8a
    ↓ manifest raw_content_hash/content_hash
public local-lab dataset_id
  3d9279e1ff8a0940336a2ac018c1b20b
    ↓ catalog alias
  local-btc-fixture
    ↓ real committed ExperimentSpec bound to this dataset
  NOT_VERIFIABLE (none found)
    ↓ committed public experiment_id / run_id / gate_run_id / scorecard_id / study_id
  NOT_VERIFIABLE (none found)
```

Evidence: `examples/research/local_lab/dataset_manifest.json:1-27`, `examples/research/local_lab/catalog.json:1-22`, and the explicit warning that this fixture is not research in `examples/research/README.md:13-16`. The example Strategy spec references a different example dataset identity, so it was not falsely joined to this chain. Private P5 identifiers and metrics were not read or inferred.

## 7. P4/P5 boundary

Public repository metadata states that the holdout is still unopened and sealed (`docs/research/p5/P5_EXECUTION_STATUS.md:4`, `:70-72`; `P5_PRE_OOS_GATE.md:4`, `:32-34`). The human pre-OOS and calendar/sample-sufficiency gates are not satisfied (`P5_EXECUTION_STATUS.md:39-50`). This auditor neither opened nor executed the holdout.

The actual private storage state, ACLs, private artifact seals, and any private metrics were not inspected and remain `NOT_VERIFIABLE`. Because A-FINDING-01/02/03/04 affect the frozen behavior or evidence identity, Auditor A recommends `BLOCK_P5` before accepting further Strategy V1 evidence, even though the public process boundary itself appears intact.

## 8. Commands, durations, results and skips

All times are wall-clock values reported by pytest or the audit wrapper. Passing counts are not inferred from interrupted commands.

| Command | Duration | Result | Notes / skips |
|---|---:|---|---|
| `python --version` | <1 s | Python **3.14.5** | Repository/AGENTS environment expects Python 3.12; results are useful but not a 3.12 runtime certification. |
| `python -m pytest tests/market_data -m "not live and not postgres and not soak" -q` | 8.18 s (9.34 s wrapper) | **172 passed, 7 deselected** | Live/Postgres/soak excluded by command. |
| `python -m pytest tests/strategy_engine tests/backtester tests/paper_trading/test_backtester_parity.py tests/paper_trading/test_backtester_signal_parity.py -m "not live and not postgres and not soak" -q` | 0.58 s (1.731 s wrapper) | **144 passed** | Offline parity only. |
| Binding/identity/resolver/double-run subset | 3.26 s (4.037 s wrapper) | **19 passed** | Exact files: `test_dataset_binding.py`, `test_identity.py`, `test_resolver_injection.py`, `test_double_run_repro.py`. |
| Registry/invalidation/compare subset | 3.40 s (4.191 s wrapper) | **16 passed** | Existing tests do not cover later-line reactivation. |
| Gate policy/evaluator/integrity/API subset | 14.83 s (16.014 s wrapper) | **73 passed**, 1 warning | Warning: Starlette/httpx deprecation only. |
| Scorecard evaluator/detail/E2E/artifact-content subset | 14.27 s (15.405 s wrapper) | **53 passed, 1 skipped**, 1 warning | One test explicitly skipped by suite; no claim for it. |
| Validation Study/API/Research read API subset | 18.20 s (19.083 s wrapper) | **57 passed**, 1 warning | Synthetic/local fixtures. |
| `npx vitest run` on four Research identity-binding files | 0.898 s (2.103 s wrapper) | **4 files, 44 tests passed** | No browser/deployment. |
| Unknown-Strategy-parameter Python probe | 0.4 s | **Negative reproduced** | `UNKNOWN_PARAMETER_ACCEPTED=True`; effective breakout lookback remained default 20. |
| Experiment invalidation temp-directory probe | 0.8 s | **Negative reproduced** | `invalidated → complete` after later JSONL line while sidecar remained. |
| Production-style Monthly input in-memory probe | 0.6 s | **Negative reproduced** | Disabled merge accepted differing native monthly (`VALID`, no conflict); enabled merge rejected it (`INVALID`, conflict). |
| Signal-intent enum probe | 0.4 s | **Negative reproduced** | No exit kind; Monthly exit reason only declarative. |
| `python -m pytest tests/market_data/test_postgres_catalog.py -q` | 2.34 s (3.298 s wrapper) | **3 passed, 1 teardown error** | Tests themselves passed. Session teardown hit `NotImplementedError` at irreversible migration 011, then an Alembic downgrade deadlock. No further DB tests/repair performed. This is not a green suite. |
| Combined broad pytest attempt | 63.5 s | **Timed out; no result claimed** | Process ended with timeout/pytest stdout `OSError`; superseded by the smaller reported suites. |
| `python -m alembic current` | 1.1 s | **Failed / no state observed** | Default configured database was unavailable. No migration or repair was performed. |

Focused passing total reported above: **578 passed, 1 skipped**, plus **3 PostgreSQL test bodies passed with 1 teardown error**. The totals exclude the timed-out attempt.

Not run by Auditor A: full CI-shaped pytest, live tests, soak tests, P5 runs, network tests, `npm run build`, browser smoke, deployed runtime probes, production database probes. They must not be reported as passed.

## 9. Candidate findings

### A-FINDING-01 — Frozen Monthly-Regime exit is not executable

- **Severity:** P1 / High.
- **Soll:** At the monthly event, a false regime generates `RC_EXIT_REGIME_MONTHLY`; execution occurs at the next daily close (`docs/strategy-specification.md:358-364`).
- **Ist:** The reason code is declared, but the Strategy output vocabulary has no exit intent and no implementation/test references the code outside the enum. Backtester and Paper act only on `LONG_ENTRY`.
- **Reproduction:** `rg -n "RC_EXIT_REGIME_MONTHLY" services tests` returns only `services/strategy_engine/models.py:44`; enum probe shows no exit kind.
- **Impact / financial-safety risk:** Positions can remain open after the frozen strategy says to exit, changing exposure, drawdown, duration, costs, PnL and every research/paper result spanning a regime fall. Backtest↔Paper parity can still be green because both omit the same behavior.
- **Confidence:** High.
- **Stop criterion:** Block P5 evidence acceptance/promotion and any claim that Strategy V1.0 runtime matches the frozen specification until the contract is resolved by a dedicated issue/decision and a regression test covers both Backtest and Paper. Do not silently change the frozen parameter/behavior contract.
- **Suggested regression:** Open a position, transition the last closed monthly series from `RegimeLong=true` to false, assert exactly one persisted/queued regime-exit command with `RC_EXIT_REGIME_MONTHLY`, next-daily-close timing, idempotent replay, and identical Backtest/Paper economic result.

### A-FINDING-02 — Unknown research Strategy parameters are identity-bound but silently ignored at execution

- **Severity:** P1 / High.
- **Soll:** Resolver explicitly says unknown keys fail (`services/research/strategy_resolver.py:160-167`); ExperimentSpec must pin the effective configuration.
- **Ist:** `ExperimentSpec.parameters` accepts arbitrary keys and hashes them into experiment/run identity, while `StrategyParameters` silently drops extras because it lacks `extra="forbid"`.
- **Reproduction:** `StrategyParameters.model_validate({'breakout_lookback': 20, 'misspelled_parameter': 999})` succeeds; the probe printed `UNKNOWN_PARAMETER_ACCEPTED=True` and kept the effective default. The same extra key remains semantic input via `services/research/identity.py:29-52`.
- **Impact / financial-safety risk:** A sealed artifact can state/hash a parameter that the engine never used. Typos produce distinct apparently pinned runs with unchanged economics, breaking provenance, candidate-freeze assurance and trustworthy comparison.
- **Confidence:** High.
- **Stop criterion:** Block P5 evidence whose declared parameters have not been validated against the exact executable Strategy schema; invalidate/re-qualify any affected evidence without mutating originals.
- **Suggested regression:** Resolve an ExperimentSpec containing one misspelled key and assert fail-closed before `experiment_id`/artifacts/run; assert every accepted semantic parameter appears with the same value in the resolved `StrategyParameters` snapshot.

### A-FINDING-03 — Paper production-style Monthly input bypasses the daily-derived conflict gate used by research

- **Severity:** P1 / High.
- **Soll:** Research uses complete monthly aggregates from daily data; native versus aggregate disagreement invalidates the bundle rather than choosing one silently (`docs/market-data-contract.md:73-79`; merge code `services/market_data/bundle.py:93-116`).
- **Ist:** Research export derives monthly from daily, but Paper `ProductionContextBuilder` calls the bundle with `aggregate_higher_timeframes=False`, so a valid-but-different native monthly candle is consumed without `MD_DUPLICATE_CONFLICT`.
- **Reproduction:** In-memory probe: disabled merge produced `VALID`, consumed the differing native monthly close, `PRODUCTION_STYLE_CONFLICT=False`; enabled merge on identical repository produced `INVALID`, conflict true.
- **Impact / financial-safety risk:** Monthly regime and therefore entries (and the contractually required exit once implemented) can differ between Research/Backtest and operational Paper even when strategy code/parameters match. Existing identical-bundle parity tests cannot detect this source divergence.
- **Confidence:** High for code-path divergence; Medium for realized provider divergence because no deployed/provider runtime was observed.
- **Stop criterion:** Block a full Backtest↔Paper input-parity claim and P5/P6 promotion reliance until the authoritative monthly source is one contract or a production-path test proves byte/economic equivalence and fails closed on disagreement.
- **Suggested regression:** Feed daily plus a structurally valid conflicting native monthly candle through the actual `ProductionContextBuilder`; assert either daily-derived monthly is authoritative or readiness is blocked with `MD_DUPLICATE_CONFLICT`. Compare the exact `CandleSeries` passed to Backtest and Paper.

### A-FINDING-04 — Experiment invalidation sidecar is not binding on lookup/reconstruction

- **Severity:** P1 / High.
- **Soll:** Invalidated historical evidence stays invalidated; originals remain immutable; no silent reactivation (`docs/research/INVALIDATION.md:1-16`).
- **Ist:** `invalidate()` writes sidecar plus superseding registry line, but `show()` returns the latest matching JSONL line without checking the sidecar. `reconstruct_from_artifacts()` derives `complete` from the immutable RunManifest and also ignores sidecars.
- **Reproduction:** In a temporary registry, append complete → invalidate → append the original complete line. `show(..., verify=False)` returned `complete` while `SIDECAR_EXISTS=True`.
- **Impact / financial-safety risk:** Registry repair/manual append/corruption can revive evidence explicitly invalidated for bad data or methodology. Downstream gates/scorecards that trust registry status may then consume it.
- **Confidence:** High.
- **Stop criterion:** Block any decision graph whose base run invalidation status has not been independently reconciled with sidecars. If reactivation is observed for real evidence, halt promotion and treat all descendants as untrusted pending append-only invalidation review.
- **Suggested regression:** After invalidation, append/reconstruct a complete entry and assert `show`, list, GateEvaluator, ScorecardEvaluator and ValidationStudy all remain invalidated/fail closed; unreadable sidecar must also fail closed.

### A-FINDING-05 — PostgreSQL raw artifact registration silently accepts conflicting `raw_dataset_id`

- **Severity:** P1 / High.
- **Soll:** A reused raw ID with different bytes/hash is an identity conflict; raw payload provenance must be immutable (`docs/market-data-contract.md:49-65`). In-memory catalog already enforces this (`services/market_data/dataset_catalog.py:64-70`).
- **Ist:** PostgreSQL uses `ON CONFLICT (raw_dataset_id) DO NOTHING` and never compares the existing row. `publish_dataset()` verifies only the foreign-key ID, not equality between manifest `raw_content_hash` and the registered raw row.
- **Reproduction:** Static executable path at `services/market_data/postgres_catalog.py:24-79`; migration makes `raw_dataset_id` the PK (`migrations/versions/010_market_data_datasets.py:23-36`). Existing Postgres tests cover candle conflicts/quality only (`tests/market_data/test_postgres_catalog.py:50-119`). No further DB mutation was performed after teardown contention.
- **Impact / financial-safety risk:** A manifest can reference a raw observation ID whose stored bytes/hash differ from the manifest claim, breaking the chain needed to reproduce or audit research inputs.
- **Confidence:** High for code behavior; real catalog impact `NOT_VERIFIABLE`.
- **Stop criterion:** Do not accept datasets into P5 where registered raw-row hash/path cannot be read back and matched to `manifest.raw_dataset_id/raw_content_hash`. Any mismatch quarantines the dataset and descendants.
- **Suggested regression:** Register raw ID/hash A, register same ID/hash B, require explicit conflict and unchanged row; publishing a manifest whose `raw_content_hash` differs from the referenced raw row must fail.

### A-FINDING-06 — Architecture document still describes pre-P3 storage

- **Severity:** P2 / Medium.
- **Soll:** GitHub/docs are project memory and architecture must label current implemented state accurately.
- **Ist:** ROADMAP marks P3 complete, code and migrations implement raw/catalog/normalized persistence, but `docs/ARCHITECTURE.md:96`, `:121-122` says no durable catalog/candles and only migrations 001-009.
- **Reproduction:** Compare those lines with `ROADMAP.md:38`, `:353`, `services/market_data/postgres_catalog.py`, and migrations 010/011.
- **Impact:** Reviewers may audit the wrong persistence boundary, omit backup/provenance controls, or incorrectly classify P3 as absent. No direct order/capital effect by itself.
- **Confidence:** High.
- **Stop criterion:** Does not independently block Paper. It blocks using `docs/ARCHITECTURE.md` as current P3 runtime evidence until reconciled.
- **Suggested regression:** Documentation contract test or release checklist assertion that listed migration head/storage responsibilities match implemented modules and ROADMAP phase status.

## 10. Overall scope conclusion

Market Data validation, deterministic aggregation, shared Strategy evaluation, artifact checksums, Gate/Scorecard seals, and Research API/UI identity have strong synthetic/offline coverage. That coverage does not justify continuing to P5 evidence acceptance because five independent integrity contradictions remain: one frozen Strategy behavior is absent, declared Strategy parameters can differ from effective parameters, production Paper monthly inputs can diverge from Research, invalidated experiments can be reactivated at the registry layer, and PostgreSQL raw provenance can silently mismatch.

No conclusion is made about deployed Runtime correctness, private P5 artifact correctness, Paper accounting, Risk Engine enforcement, execution ownership, API security, or deployment SHA parity; those are either `NOT_VERIFIABLE` here or assigned to other auditors.
