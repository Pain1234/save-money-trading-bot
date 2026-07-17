# P4 Research Workspace — follow-up issues (Issue #240)

This document prepares **separate** follow-up issues after the read-only vertical
slice (#240). Do **not** implement these in the #240 PR.

## Recommended issue split

### 1. P4.6 Strategy Lab und Experiment-Konfiguration

**Goal:** UI to compose/edit ExperimentSpec and validate against schema before a run.

**Suggested further split (recommended):**

| Sub-issue | Scope |
|-----------|--------|
| P4.6a Strategy Lab form shell | Route `/dashboard/research/lab`, form layout, dry-run validation only |
| P4.6b Spec builder + schema errors | Bind form fields to ExperimentSpec; show JSON schema errors |
| P4.6c Dataset / cost / benchmark pickers | Select existing dataset manifests, cost model version, benchmark refs |

**Out of scope for Lab alone:** starting runs (see async runner).

### 2. P4.6 Async Research Runs und Job-Status

**Goal:** Start research runs from the workspace with durable job status (not CLI-only).

**Suggested further split (recommended — size warrants it):**

| Sub-issue | Scope |
|-----------|--------|
| P4.6d Job model + status API | Job records (filesystem or DB), `GET` status; no queue yet |
| P4.6e Worker / queue adapter | Async execution of `run_experiment`; cancel/retry policy |
| P4.6f Run controls UI | Start from Lab; progress / failed / complete surfaces |

**Out of scope:** Promotion, gates, live trading.

### 3. P4.7 Experiment- und Strategie-Vergleich

Compare View over existing registry entries / metrics artifacts (reuse
`ExperimentRegistry.compare` semantics where possible).

### 4. P4.7 Robustness-Orchestrierung

Wire existing P5 helpers (walk-forward, cost stress, parameter stability,
bootstrap) into orchestrated runs + UI surfaces — no new backtester.

### 5. P4.7 Versionierter Gate Evaluator und Gate-Persistenz

Gate evaluation versioning, persistence of accept/reject reasons, no silent
promotion into paper trading.

### 6. P4.8 End-to-End-, Reproduzierbarkeits- und UI-Abnahmetests

Playwright + API acceptance covering Lab → run → detail → compare; double-run
repro checks; no mock production data.

## Milestone note

Milestone remains **P4 – Research Engine und Research Workspace V1**.
P5 stays blocked until Engine + Read-API + Workspace are jointly usable enough
(read path from #240 is the first workspace slice).

Open these as separate GitHub issues after #240 merges (do not bundle into #240).
Issue numbers can be linked back into this document once filed.