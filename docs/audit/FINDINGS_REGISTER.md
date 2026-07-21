# Findings Register

Audit issue: [#371](https://github.com/Pain1234/save-money-trading-bot/issues/371)
Evidence SHA: `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`

Counts: **P0 0 · P1 14 · P2 10 · P3 1 · INFO 3**. Candidate IDs from the
independent reports are mapped here to stable audit IDs. No remediation issue was created.

## AUD-P1-001 – Frozen Monthly-regime exit is not executable

### Behauptetes Sollverhalten
Strategy V1 exits when the documented Monthly regime condition fails.

### Tatsächliches Verhalten
The reason enum exists, but no executable exit intent or Backtester/Paper consumer path exists.

### Evidenz
- `docs/strategy-specification.md:60,331,358-364`
- `services/strategy_engine/models.py:44,67-72`
- `services/backtester/engine.py:563-599`; `services/paper_trading/evaluation.py:139-147`
- Auditor A executable-enum probe; no matching implementation/test found.

### Reproduktion
1. Compare the frozen exit table with the Strategy intent enum.
2. Trace every intent consumer in Backtester and Paper; only long entry is consumed.

### Auswirkung
Strategy V1 behavior and its accepted evidence do not match the frozen contract.

### Sicherheits- oder Finanzrisiko
Paper/Research can retain positions under a regime where the contract requires exit.

### Ursache
Bestätigt: specification feature was not wired into the executable lifecycle.

### Empfohlene Abhilfe
Human decision on contract versus implementation, then a dedicated issue/PR and parity regression.

### Betroffene Bereiche
Strategy, Backtester, Paper, Research evidence.

### Regressionstest
Monthly-regime transition must produce the same exit time/reason in Strategy, Backtester and Paper.

### Confidence
HIGH. Stop criterion: block P5 evidence acceptance until reconciled.

## AUD-P1-002 – Unknown Research parameters are identity-bound but ignored

### Behauptetes Sollverhalten
Unknown Strategy parameters fail validation; the run ID represents the effective configuration.

### Tatsächliches Verhalten
Free-form keys enter semantic identity, while Pydantic silently ignores them and executes defaults.

### Evidenz
- `docs/research/EXPERIMENT_SPEC.md:9-25`
- `services/research/experiment_spec.py:127-159`; `strategy_resolver.py:160-167`
- `services/strategy_engine/models.py:115-131`
- Negative probe accepted `misspelled_parameter` and resolved the default.

### Reproduktion
1. Add an unknown key to a valid ExperimentSpec.
2. Resolve StrategyParameters and compare identity input with effective values.

### Auswirkung
Different declared experiments can execute equivalent defaults while appearing uniquely configured.

### Sicherheits- oder Finanzrisiko
Run/gate/scorecard provenance can certify behavior that was not actually configured.

### Ursache
Bestätigt: missing `extra="forbid"`/effective-config binding.

### Empfohlene Abhilfe
Reject unknown keys and bind the canonical effective config, with migration/invalidation review.

### Betroffene Bereiche
Research identity, Strategy config, gates, scorecards.

### Regressionstest
Unknown or misspelled key must fail before a run ID/job is created.

### Confidence
HIGH. Stop criterion: block P5 evidence created through this path.

## AUD-P1-003 – Paper higher-timeframe data bypasses the Research conflict gate

### Behauptetes Sollverhalten
Weekly/monthly candles derive from complete parents and native-vs-derived disagreement fails closed.

### Tatsächliches Verhalten
The Paper production-style repository disables higher-timeframe merge/conflict checking and accepts a differing native Monthly candle.

### Evidenz
- `services/market_data/aggregation.py:21-145`
- `services/research/hl_dataset_export.py:300-315`
- Synthetic native-Monthly mismatch: `aggregate_higher_timeframes=False` returned VALID; merge enabled returned `MD_DUPLICATE_CONFLICT`.

### Reproduktion
1. Build complete daily parents and a structurally valid native month with a different close.
2. Validate with Paper-style aggregation disabled, then with merge enabled.

### Auswirkung
Research and Paper can evaluate different regime inputs from ostensibly identical data.

### Sicherheits- oder Finanzrisiko
Signal/parity evidence can be contaminated without a visible data-quality failure.

### Ursache
Bestätigt: production-style repository configuration bypasses comparison.

### Empfohlene Abhilfe
Define one authoritative provenance path and make disagreement fail closed.

### Betroffene Bereiche
Market Data, Strategy regime input, Backtest/Paper parity.

### Regressionstest
Native/derived mismatch must reject the Paper input before Strategy evaluation.

### Confidence
HIGH. Stop criterion: do not accept affected parity/P5 evidence.

## AUD-P1-004 – Invalidated experiment evidence can reactivate

### Behauptetes Sollverhalten
Invalidation is durable and all lookup/reconstruction paths remain fail-closed.

### Tatsächliches Verhalten
Lookup trusts the latest JSONL line and reconstruction can append `complete` while the invalidation sidecar still exists.

### Evidenz
- `docs/research/INVALIDATION.md:1-16`
- `services/research/registry.py:133-187,240-288`
- Temp negative test observed `invalidated → complete` with sidecar present.

### Reproduktion
1. Register and invalidate a temporary completed run.
2. Append/reconstruct a later complete registry record and call `show()`.

### Auswirkung
Explicitly rejected evidence can re-enter gates/scorecards.

### Sicherheits- oder Finanzrisiko
Research acceptance may use known-invalid results.

### Ursache
Bestätigt: invalidation sidecar is not part of resolution precedence.

### Empfohlene Abhilfe
Make invalidation binding in every read/rebuild path; audit existing registries.

### Betroffene Bereiche
Registry, gates, scorecards, validation studies.

### Regressionstest
All append/rebuild permutations must preserve invalidated status.

### Confidence
HIGH. Stop criterion: block P5 evidence consumption until fixed/audited.

## AUD-P1-005 – PostgreSQL raw Dataset ID collision fails open

### Behauptetes Sollverhalten
A `raw_dataset_id` uniquely identifies the exact raw content and manifest hash.

### Tatsächliches Verhalten
PostgreSQL registration uses conflict-do-nothing without verifying existing content; manifest publish does not compare the raw row hash.

### Evidenz
- `docs/market-data-contract.md:49-65,86-102`
- `services/market_data/dataset_catalog.py:64-70`
- `services/market_data/postgres_catalog.py:24-79`
- Existing Postgres tests lack duplicate-ID/different-content negative coverage.

### Reproduktion
1. Register a raw ID and content hash.
2. Register the same ID with different content and publish a manifest referencing it.

### Auswirkung
Catalog provenance can point to content different from the manifest claim.

### Sicherheits- oder Finanzrisiko
Research datasets/runs may be non-reproducible or misbound.

### Ursache
Bestätigt in code; deployed occurrence unknown.

### Empfohlene Abhilfe
Compare existing identity atomically and reject mismatches; audit stored rows.

### Betroffene Bereiche
PostgreSQL catalog, raw store, manifests, Research provenance.

### Regressionstest
Concurrent and sequential conflicting registrations must fail without publishing.

### Confidence
HIGH for behavior; runtime impact NOT_VERIFIABLE. Stop criterion: block new P5 evidence from unverified catalog rows.

## AUD-P1-006 – Control pause does not block production intent creation

### Behauptetes Sollverhalten
An accepted pause blocks all new intents/entries.

### Tatsächliches Verhalten
API persists `runtime.paused`, but production context compares the runtime status enum instead.

### Evidenz
- `services/paper_trading/api.py:525-535`
- `services/paper_trading/scheduler_context.py:91-98`
- Safe reproduction with READY + `paused=True` returned gates `(True, False, False)`.

### Reproduktion
1. Construct READY runtime state with persisted pause true.
2. Invoke production `_runtime_gates()` and inspect `entry_ready/paused`.

### Auswirkung
Operator receives “paused” while new intents remain possible.

### Sicherheits- oder Finanzrisiko
Paper positions can be opened after a supposed safety action.

### Ursache
Bestätigt: wrong runtime field wired.

### Empfohlene Abhilfe
Unify pause state and prove production-path blocking.

### Betroffene Bereiche
Control API, scheduler context, Paper execution.

### Regressionstest
API pause followed by scheduler evaluation must create neither intent nor fill.

### Confidence
HIGH. Stop criterion: do not rely on control pause; stop worker for freeze; block unsupervised Paper/P6.

## AUD-P1-007 – Scheduled entries bypass later pause, kill and readiness

### Behauptetes Sollverhalten
Unsafe state is rechecked immediately before any new risk is opened.

### Tatsächliches Verhalten
FillProcessingContext has no runtime gates; pending fill path passes ACTIVE to Risk by default.

### Evidenz
- `services/paper_trading/lifecycle.py:103-115,242-319`
- `services/backtester/paper_lifecycle.py:108-150`
- Interface/call-chain trace; no negative regression exists.

### Reproduktion
1. Schedule an entry while READY.
2. Change pause/kill/readiness before next open and execute due-fill path.

### Auswirkung
A position can open after the system has become unsafe.

### Sicherheits- oder Finanzrisiko
Paper risk gates are time-of-check-only, not final authorization.

### Ursache
Bestätigt: runtime state absent from fill contract.

### Empfohlene Abhilfe
Fail-closed final authorization at fill time and cancel/expire pending risk.

### Betroffene Bereiche
Scheduler, Paper lifecycle, Risk adapter.

### Regressionstest
Pause, kill, stale heartbeat and degraded readiness must each block a pending fill.

### Confidence
HIGH. Stop criterion: stop worker before a due open after any unsafe transition; block unsupervised Paper/P6.

## AUD-P1-008 – Startup can become READY without economic reconciliation

### Behauptetes Sollverhalten
Wallet/position/accounting mismatch causes ERROR/freeze on restart.

### Tatsächliches Verhalten
Startup recovery checks structure/existence but never invokes independent accounting verification.

### Evidenz
- `docs/risk-specification.md:292-298`
- `services/paper_trading/recovery.py:84-93,143-163,193-209`
- `services/paper_trading/accounting_verification.py`

### Reproduktion
1. In an isolated test DB, create a coherent fill/position chain and corrupt wallet cash.
2. Run startup recovery and compare readiness with independent verifier result.

### Auswirkung
Sizing, dashboard and later PnL may proceed from corrupted balances.

### Sicherheits- oder Finanzrisiko
New paper risk can be based on incorrect equity.

### Ursache
Bestätigt by call graph; DB occurrence/reproduction not executed due unsafe shared test DB.

### Empfohlene Abhilfe
Bind sealed independent reconciliation into readiness/startup.

### Betroffene Bereiche
Recovery, readiness, wallet, Risk, monitoring.

### Regressionstest
Any wallet/event mismatch must keep runtime non-READY and emit an incident.

### Confidence
HIGH for code. Stop criterion: external reconciliation plus worker stop after uncertain restart; block unsupervised Paper/P6.

## AUD-P1-009 – Production equity snapshots omit market marks

### Behauptetes Sollverhalten
Equity equals cash plus mark-to-market open PnL and Dashboard/API reflect it.

### Tatsächliches Verhalten
Production snapshot callers pass no marks; missing marks fall back to entry, yielding unrealized zero and equity=cash.

### Evidenz
- `services/paper_trading/scheduler.py:486-493`; `stops.py:160-164`
- `services/backtester/portfolio.py:34-43`
- Pure reproduction: entry 50,000, mark 60,000, qty 0.1 expected +1,000; unmarked snapshot returned zero.

### Reproduktion
1. Open a Paper position and compute with a non-entry mark.
2. Compare mark-aware function with scheduled snapshot call.

### Auswirkung
Equity curve, drawdown, unrealized PnL and soak evidence are economically wrong while positions are open.

### Sicherheits- oder Finanzrisiko
Operators and promotion decisions can rely on false loss/profit information.

### Ursache
Bestätigt: mark map omitted by production callers.

### Empfohlene Abhilfe
Persist mark provenance and test DB→API→UI economic equality.

### Betroffene Bereiche
Paper accounting, snapshots, API, dashboard, P6 evidence.

### Regressionstest
Open-position price move must update DB/API/UI equity and unrealized PnL exactly once.

### Confidence
HIGH. Stop criterion: do not use open-position dashboard economics or begin P6.

## AUD-P1-010 – Gap-stop fill contradicts frozen exact-Open price

### Behauptetes Sollverhalten
When Open gaps through the stop, V1 fills exactly at Open.

### Tatsächliches Verhalten
Code selects Open as reference, then applies generic adverse exit slippage.

### Evidenz
- `docs/risk-specification.md:260-273`
- `services/paper_trading/stops.py:261-267`
- `services/backtester/paper_lifecycle.py:246-260`
- Scenario expected 47,000 but persisted formula produced 46,976.5.

### Reproduktion
1. Create a long whose next Open is below stop.
2. Evaluate trigger and fill price with frozen slippage config.

### Auswirkung
Realized PnL, cash, fees and parity differ from the declared model.

### Sicherheits- oder Finanzrisiko
Conservative error still invalidates economic comparability and phase evidence.

### Ursache
Bestätigt: generic slippage applied after special gap rule.

### Empfohlene Abhilfe
Human decision on authoritative frozen assumption, then one implementation/test contract.

### Betroffene Bereiche
Stops, execution, accounting, Backtest/Paper parity.

### Regressionstest
Gap and non-gap exits must assert exact governed price transformation.

### Confidence
HIGH. Stop criterion: exclude affected results from P5/P6 parity and decay decisions.

## AUD-P1-011 – Independent reconciliation omits funding

### Behauptetes Sollverhalten
Funding is zero/fail-closed in V1 and any future amount reconciles exactly once to events.

### Tatsächliches Verhalten
ReconstructedWallet has no funding field and verifier never compares `wallet.total_funding`.

### Evidenz
- `services/paper_trading/accounting_verification.py:12-140`
- Funding remains disabled by current deployment contract.

### Reproduktion
1. Supply a wallet with nonzero total funding and no funding event.
2. Run independent accounting verification; no funding issue is produced.

### Auswirkung
Corrupt/nonzero funding can be displayed without independent detection.

### Sicherheits- oder Finanzrisiko
Wrong PnL if funding is ever activated or corrupted.

### Ursache
Bestätigt: field/check absent.

### Empfohlene Abhilfe
Keep disabled; add event-to-wallet zero/equality proof before activation.

### Betroffene Bereiche
Accounting, reconciliation, API/dashboard.

### Regressionstest
Unexpected nonzero and duplicate funding must fail reconciliation/readiness.

### Confidence
HIGH. Stop criterion: keep `funding_enabled=False`; no P6 funding-reconciled claim.

## AUD-P1-012 – Worker handover can clobber successor runtime state

### Behauptetes Sollverhalten
Ownership handover is atomic and a predecessor cannot modify shared state after unlock.

### Tatsächliches Verhalten
Shutdown releases advisory lock before writing final STOPPED, allowing a successor interleaving.

### Evidenz
- `services/paper_trading/application.py:355-362`
- `services/paper_trading/db/repository.py:111-131`
- Code-reachable sequence documented in `ARCHITECTURE_RUNTIME_MAP.md`.

### Reproduktion
1. Pause worker A between unlock and STOPPED write.
2. Start worker B, acquire lock/recover, then resume A.

### Auswirkung
Runtime readiness/state can become stale during rolling restart.

### Sicherheits- oder Finanzrisiko
Timing-dependent scheduler behavior and ambiguous owner state; duplicate fill not directly proven.

### Ursache
Wahrscheinlich/Code-reachable; two-process DB test not executed.

### Empfohlene Abhilfe
Atomic/fenced handover with compare-and-swap ownership token.

### Betroffene Bereiche
Worker lifecycle, runtime singleton, operations.

### Regressionstest
Two-process deterministic barrier test must prove predecessor writes are rejected after unlock.

### Confidence
MEDIUM. Stop criterion: no rolling overlap; scale to zero and verify predecessor exit before successor.

## AUD-P1-013 – Research write backend has no backend authentication

### Behauptetes Sollverhalten
Research is read-only, or any write plane is authenticated and isolated.

### Tatsächliches Verhalten
The combined read API mounts Research POST routes without backend auth; Dashboard session protection is only in the proxy/UI layer.

### Evidenz
- `services/paper_trading/readonly_api.py:95`
- `services/research/api.py:370-769`
- API inventory and 75 focused API/security tests.
- Runtime private-network placement is NOT_VERIFIABLE.

### Reproduktion
1. Build the read API app directly.
2. Call Research create/start/evaluate/invalidate POST endpoints without a service credential.

### Auswirkung
Any caller reaching the backend can mutate research evidence or start jobs.

### Sicherheits- oder Finanzrisiko
Read-only boundary and P5 evidence integrity depend only on unverified network configuration.

### Ursache
Bestätigt in code; runtime reachability unknown.

### Empfohlene Abhilfe
Human decision on write-plane contract; then backend auth, least privilege and verified isolation.

### Betroffene Bereiche
Research API, Dashboard proxy, deployment/security, P5 evidence.

### Regressionstest
Direct unauthenticated POST must fail before any repository mutation.

### Confidence
HIGH for code. Stop criterion: block P5/final evidence mutations; monitoring GET may continue.

## AUD-P1-014 – Python production image is not dependency-reproducible

### Behauptetes Sollverhalten
Same Git SHA rebuilds the same executable dependency set.

### Tatsächliches Verhalten
Python image installs lower-bound `pyproject.toml` dependencies and ignores the pinned baseline; Node correctly uses its lockfile.

### Evidenz
- `deploy/Dockerfile.paper-python:20-28`
- `pyproject.toml` lower-bound dependencies
- `requirements-baseline.txt` exists but is not installed in image.

### Reproduktion
1. Inspect image build inputs/command.
2. Rebuild at different resolver dates and compare frozen manifests/image digests.

### Auswirkung
Repository SHA equality does not prove API/worker behavior equality.

### Sicherheits- oder Finanzrisiko
Research/Paper results and safety behavior may change under the same claimed code revision.

### Ursache
Bestätigt: deployment path bypasses pinned baseline.

### Empfohlene Abhilfe
Build from reviewed hashes/lock and publish immutable image/dependency provenance.

### Betroffene Bereiche
API, worker, CI/CD, Research reproducibility.

### Regressionstest
Two isolated same-SHA builds must record equivalent locked dependency identity.

### Confidence
HIGH. Stop criterion: do not use rebuilt image as promotion evidence without recorded/matched digest.

## AUD-P2-001 – Architecture documentation describes pre-P3 persistence

### Behauptetes Sollverhalten
Architecture is the current system map.

### Tatsächliches Verhalten
It says market data/catalog is in-memory and migrations stop at 009; code/ROADMAP implement durable catalog and 010/011.

### Evidenz
- `docs/ARCHITECTURE.md:96,121-122`; `ROADMAP.md:38,353`
- `services/market_data`; `services/paper_trading/db/migrations/versions/010*`, `011*`

### Reproduktion
1. Compare document inventory with repository packages/migrations.

### Auswirkung
Review/backup/threat models target the wrong boundary.

### Sicherheits- oder Finanzrisiko
Indirect provenance/operations risk; no direct trade effect.

### Ursache
Bestätigt documentation drift.

### Empfohlene Abhilfe
Dedicated architecture update after behavior findings are decided.

### Betroffene Bereiche
Architecture, Market Data, operations.

### Regressionstest
Doc inventory check or review checklist for migrations/services.

### Confidence
HIGH.

## AUD-P2-002 – Partial fills, cancel/replace and persistent protective orders are scaffolding

### Behauptetes Sollverhalten
Order lifecycle handles partial/cancel transitions and resizes/removes protective stops.

### Tatsächliches Verhalten
Paper path performs one full fill; enums/schema exist without the described lifecycle or persisted stop order.

### Evidenz
- `services/paper_trading/execution.py:358-390`
- Repository trace in `RISK_AND_EXECUTION_AUDIT.md`; no end-to-end transition test.

### Reproduktion
1. Trace CREATED through fill/cancel states and search all transition writers.

### Auswirkung
Documentation/tests can overstate readiness for richer execution.

### Sicherheits- oder Finanzrisiko
Future live-readiness decisions could rely on nonexistent safety behavior.

### Ursache
Bestätigt: model scaffolding ahead of implementation.

### Empfohlene Abhilfe
Label NOT_IMPLEMENTED; require dedicated future scope before use.

### Betroffene Bereiche
Order lifecycle, stops, P8 planning.

### Regressionstest
State-machine negative/partial/cancel/reconnect tests before any activation.

### Confidence
HIGH.

## AUD-P2-003 – Running service SHA and image digest are not observable

### Behauptetes Sollverhalten
Dashboard/API/worker deployment parity can be independently proven.

### Tatsächliches Verhalten
Health/status/UI expose neither commit nor image digest; only public login was visible.

### Evidenz
- `deploy/Dockerfile.paper-python`; `deploy/Dockerfile.dashboard`; start scripts
- Public observation `https://bot.save-money.xyz/login?next=%2Fdashboard`

### Reproduktion
1. Inspect public health/login and status schemas for build identity.

### Auswirkung
Deployment drift cannot be detected from available runtime evidence.

### Sicherheits- oder Finanzrisiko
Unknown code may be mistaken for audited SHA.

### Ursache
Bestätigt observability gap; actual drift unknown.

### Empfohlene Abhilfe
Expose safe internal build metadata without public debug/config leakage.

### Betroffene Bereiche
Deployment, API, Dashboard, operations.

### Regressionstest
Deployment verification job matches all three service SHAs/digests and DB fingerprint.

### Confidence
HIGH.

## AUD-P2-004 – Audit payload redaction is shallow

### Behauptetes Sollverhalten
Audit-event responses never disclose secrets.

### Tatsächliches Verhalten
Only selected top-level keys are redacted; nested values and aliases such as token/authorization can survive.

### Evidenz
- Sanitizer trace and synthetic marker test in `SECURITY_AUDIT.md`.

### Reproduktion
1. Pass nested dictionaries/lists with synthetic credential aliases to sanitizer.
2. Serialize the returned event.

### Auswirkung
Authenticated API consumers could receive a secret if a producer persists one.

### Sicherheits- oder Finanzrisiko
Potential credential disclosure; no actual secret-bearing event was found.

### Ursache
Bestätigt shallow allow/deny logic.

### Empfohlene Abhilfe
Schema allow-list/recursive redaction and producer provenance review.

### Betroffene Bereiche
Paper API, audit events, security.

### Regressionstest
Nested/aliased synthetic markers must never survive serialization.

### Confidence
HIGH for behavior; occurrence unknown.

## AUD-P2-005 – Failed Research recovery does not disable later writes

### Behauptetes Sollverhalten
Unknown job ownership after recovery failure is read-only/fail-closed.

### Tatsächliches Verhalten
Startup logs recovery failure but keeps create/start/evaluate/invalidate routes writable.

### Evidenz
- Startup/recovery and route trace in `RESILIENCE_AUDIT.md`.

### Reproduktion
1. Force orphan-recovery exception.
2. Call Research mutation endpoints in the same process.

### Auswirkung
Unknown ownership can be compounded by new jobs/evidence changes.

### Sicherheits- oder Finanzrisiko
Duplicate/ambiguous Research job state and provenance.

### Ursache
Bestätigt in code; runtime occurrence unknown.

### Empfohlene Abhilfe
Shared degraded write gate until reconciliation succeeds.

### Betroffene Bereiche
Research recovery, API, job registry.

### Regressionstest
All writes return unavailable after recovery failure; reads remain available.

### Confidence
HIGH.

## AUD-P2-006 – Validation UI renders verified zero failures as unavailable

### Behauptetes Sollverhalten
Zero and missing evidence are semantically distinct.

### Tatsächliches Verhalten
Falsy handling maps `n_failed=0` to “Nicht verfügbar”.

### Evidenz
- Dashboard field mapping in `API_UI_DEPLOYMENT_AUDIT.md` (C-FINDING-07).

### Reproduktion
1. Render validation detail with `n_failed=0`, then with missing value.

### Auswirkung
Users cannot distinguish clean validation from absent evidence.

### Sicherheits- oder Finanzrisiko
Human decision may be based on incorrect evidence semantics.

### Ursache
Bestätigt: truthiness used instead of null check.

### Empfohlene Abhilfe
Explicit null/missing formatting.

### Betroffene Bereiche
Research Dashboard.

### Regressionstest
Snapshot/assert distinct `0 failed` and NOT_AVAILABLE.

### Confidence
HIGH.

## AUD-P2-007 – Monitor cannot prove the active execution owner

### Behauptetes Sollverhalten
Operators can identify exactly one worker/lock owner.

### Tatsächliches Verhalten
Read API serializes advisory-lock held as false and UI omits worker instance identity.

### Evidenz
- API/Monitor mapping in `API_UI_DEPLOYMENT_AUDIT.md` (C-FINDING-08).

### Reproduktion
1. Trace status response construction and rendered fields.

### Auswirkung
Duplicate-worker diagnosis and restart verification require unavailable logs/DB access.

### Sicherheits- oder Finanzrisiko
Ownership ambiguity can extend unsafe overlap.

### Ursache
Bestätigt observability gap; actual duplicate writer not observed.

### Empfohlene Abhilfe
Expose safe owner/fencing state to authenticated operations view.

### Betroffene Bereiche
Paper API, Monitor, operations.

### Regressionstest
Read API distinguishes known owner, no owner and unknown; never serializes unknown as false.

### Confidence
HIGH.

## AUD-P2-008 – Public P5 status documents contradict each other

### Behauptetes Sollverhalten
GitHub/public docs unambiguously state policy sign-off and execution state.

### Tatsächliches Verhalten
`P5_EXECUTION_STATUS.md` describes #251-#254 as executed/complete while `P5_SCORECARD_POLICY_BIND.md` remains pending and says they must wait.

### Evidenz
- `docs/research/p5/P5_EXECUTION_STATUS.md`
- `docs/research/p5/P5_SCORECARD_POLICY_BIND.md`
- Open issues #251-#254; no private evidence inspected.

### Reproduktion
1. Compare status, policy-bind and open issue states at frozen SHA.

### Auswirkung
Auditors cannot infer which actions were approved/executed from public Source of Truth.

### Sicherheits- oder Finanzrisiko
Governance ambiguity risks unintended phase progression; no holdout contamination was observed.

### Ursache
Unbekannt; requires human reconciliation.

### Empfohlene Abhilfe
One reviewed status update referencing approvals/commits without publishing private metrics.

### Betroffene Bereiche
P5 governance, public/private boundary.

### Regressionstest
Governance checklist validates issue/doc state consistency.

### Confidence
HIGH for contradiction; private truth NOT_VERIFIABLE.

## AUD-P2-009 – Mandatory mypy gate is not reproducibly green

### Behauptetes Sollverhalten
`python -m mypy .` is a required pre-push static check.

### Tatsächliches Verhalten
It failed on missing optional script dependencies/duplicate module; configured package run initially selected editable installs, and with `MYPYPATH=services` reported 35 errors in 17 files.

### Evidenz
- `AGENTS.md`; `pyproject.toml`
- Executed mypy commands and full outputs recorded in the summary.

### Reproduktion
1. Install declared dev/api extras in Python 3.12.
2. Run `python -m mypy .`, then configured packages with repository source path.

### Auswirkung
Developers cannot satisfy the documented gate consistently; type regressions can be hidden by command/environment differences.

### Sicherheits- oder Finanzrisiko
Indirect correctness risk, concentrated in Research/Market Data typing.

### Ursache
Bestätigt configuration/dependency/source-resolution drift.

### Empfohlene Abhilfe
Define one CI-shaped command, declare stubs, and resolve real errors in dedicated PRs.

### Betroffene Bereiche
Quality gate, Research, Market Data, scripts.

### Regressionstest
Run the exact documented command in clean CI and require success.

### Confidence
HIGH.

## AUD-P2-010 – PostgreSQL audit tests are not isolated from shared local state

### Behauptetes Sollverhalten
Tests are deterministic, isolated and do not invalidate one another's schema evidence.

### Tatsächliches Verhalten
A targeted catalog teardown deadlocked while downgrading the shared test DB to migration 010; a concurrent full suite then produced 35 mixed failures, many from `current=010, head=011`. Another targeted slice saw 21 auth setup errors.

### Evidenz
- Full suite: 1,444 passed, 35 failed, 8 skipped, 29 subtests; 146.4 s.
- Isolated non-Postgres suite: 1,283 passed, 1 skipped; 65.96 s.
- Auditor A/B PostgreSQL execution records.

### Reproduktion
1. Point concurrent suites at the same local test role/database.
2. Allow migration teardown while the other suite is active.

### Auswirkung
Full-suite failures and passes cannot be attributed cleanly; teardown can change schema for peers.

### Sicherheits- oder Finanzrisiko
False assurance or false failure in restart/reconciliation/database safety evidence.

### Ursache
Bestätigt audit-environment/test-isolation problem; not classified as production defect.

### Empfohlene Abhilfe
Per-run database/schema identity and fail-closed no-default URL for destructive migration tests.

### Betroffene Bereiche
PostgreSQL tests, migrations, CI/local audit workflow.

### Regressionstest
Two concurrent isolated suites must never share/downgrade the other's schema.

### Confidence
HIGH for observed audit environment.

## AUD-P3-001 – Incident page falls back to ordinary events

### Behauptetes Sollverhalten
No matching incidents produces a clear empty state.

### Tatsächliches Verhalten
When regex matching returns zero, the page displays normal events under “Errors / Incidents”.

### Evidenz
- Dashboard trace in `API_UI_DEPLOYMENT_AUDIT.md` (C-FINDING-06).

### Reproduktion
1. Provide ordinary events with no incident match and render the page.

### Auswirkung
False operational signal; page is not a reliable incident register.

### Sicherheits- oder Finanzrisiko
Low direct risk; may distract diagnosis.

### Ursache
Bestätigt fallback behavior.

### Empfohlene Abhilfe
Render explicit empty state and retain raw-event page separately.

### Betroffene Bereiche
Monitor UI, operations.

### Regressionstest
Zero matches must render zero incident rows.

### Confidence
HIGH.

## AUD-INFO-001 – Checkout line-ending drift dirties four tracked artifacts

### Behauptetes Sollverhalten
Fresh worktree is clean and `git diff --check` evaluates only content changes.

### Tatsächliches Verhalten
Three specs appear modified solely because CRLF blobs conflict with `eol=lf`; the reporting test also rewrote its snapshot. None is staged for the audit.

### Evidenz
- Raw working hashes equal HEAD blob hashes for the three specs; `--ignore-space-at-eol` is empty.
- `git diff --check` reports their line-ending whitespace.

### Reproduktion
1. Create a fresh Windows worktree at the frozen SHA and inspect status/hashes.

### Auswirkung
No product behavior change; noisy quality-gate evidence and staging risk.

### Sicherheits- oder Finanzrisiko
None direct.

### Ursache
Bestätigt repository attributes/blob normalization drift; report snapshot was test-generated.

### Empfohlene Abhilfe
Separate human-approved normalization/test-artifact hygiene work.

### Betroffene Bereiche
Git/worktree/quality gate.

### Regressionstest
Fresh Windows/Linux checkout should be clean.

### Confidence
HIGH.

## AUD-INFO-002 – Runtime observation was limited to public login

### Behauptetes Sollverhalten
Runtime claims must cite observed service identity/state.

### Tatsächliches Verhalten
The public URL redirected to the login page and identified a read-only Paper monitor; no credentials or private service access were used.

### Evidenz
- `https://bot.save-money.xyz/login?next=%2Fdashboard`, observed during audit.

### Reproduktion
1. Open the public root without credentials.

### Auswirkung
Authenticated Dashboard, API, worker, DB, logs and Railway claims remain NOT_VERIFIABLE.

### Sicherheits- oder Finanzrisiko
No direct risk; limits audit confidence.

### Ursache
Expected access boundary.

### Empfohlene Abhilfe
Future authorized staging/runtime evidence pack, not a public debug endpoint.

### Betroffene Bereiche
Deployment/runtime audit.

### Regressionstest
N/A.

### Confidence
HIGH.

## AUD-INFO-003 – P5 holdout was not touched; private state remains unverified

### Behauptetes Sollverhalten
Audit must not open Holdout C or disclose private values.

### Tatsächliches Verhalten
No P5 action/artifact/private repository was invoked. Public metadata says sealed/blocked; actual private ACL/storage state was intentionally not inspected.

### Evidenz
- Public P5 status/calendar and open issues #204/#205.
- Audit command inventory contains no P5 execution.

### Reproduktion
1. Review audit command/test list and public status only.

### Auswirkung
Boundary preserved, but private-state correctness cannot be certified.

### Sicherheits- oder Finanzrisiko
No contamination caused by this audit.

### Ursache
Intentional scope restriction.

### Empfohlene Abhilfe
None in audit; keep blocked until P1 remediation/human approval.

### Betroffene Bereiche
P5 governance/public-private boundary.

### Regressionstest
N/A.

### Confidence
HIGH for audit actions; private state NOT_VERIFIABLE.
