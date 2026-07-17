# P4 Research Workspace — follow-up issues (Issue #240 / #242)

## Recommended issue split

### 1–2. P4.6 Strategy Lab + Async Runs — done in #242

Combined vertical slice: Strategy Lab UI, write API, filesystem job store,
in-process worker wrapping `run_experiment`, status polling.

**V1 job limit:** in-process threads do not resume after API process restart;
stale `running` jobs are failed closed on the next status read.

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
P5 stays blocked until Engine + Read-API + Workspace are jointly usable enough.
