# P4 Research Workspace — follow-up issues (Issue #240 / #242 / #265 / #266)

## Status (delivered / open)

**Delivered:** #265 — Trend Strategy V1 visible/selectable in Research (catalog + Lab). #266 — experiment detail **Kurs & Trades** chart from verified `trades.json` + run-bound `chart_data.json` candles (fail-closed integrity). #247 — Robustness-Orchestrierung (walk-forward, cost stress, parameter stability, bootstrap) auf derselben Runner/Registry/Artefakt-Linie + minimale UI unter `/dashboard/research/robustness` (siehe §4).

**Open:** #242 UI-Abnahme (Lab + catalog), #245 durable jobs, #246/#248/#249 compare/gates/validation, #250 E2E/UI acceptance; Cancel/Retry deferred.

## Recommended issue split

### 1–2. P4.6 Strategy Lab + Async Runs — done in #242 / PR #243

Combined vertical slice: Strategy Lab UI, write API, filesystem job store,
in-process worker wrapping `run_experiment`, status polling.

**V1 job limit:** in-process threads do not resume after API process restart;
stale `running` jobs are failed closed on the next status read.

**Abnahme:** #242 remains open until manual UI acceptance with a dataset catalog
(also covered by #250). Local catalog helper tracked separately (#264).

### 2b. P4.6 Make Trend Strategy V1 visible — #265

Canonical catalog identity (`trend_v1`), alias compatibility (`trend_strategy_v1`),
strategies list/detail routes, Lab display names — strategy must appear even with
zero experiments. No second registry; resolver remains SoT.

### 2c. P4.7 Price and trade chart — #266

Depends on PR #243 (merged) and stable canonical strategy id (#265). Experiment
detail „Kurs & Trades“ from verified `trades.json` + bound dataset candles;
fail-closed integrity. Does not replace equity/drawdown charts.

Numbering note: existing #246–#249 remain P4.7a–d (compare / robustness / gates /
validation). #266 is the price/trade chart slice under the same milestone.

### 3. P4.7a Experiment- und Strategie-Vergleich — #246

Compare View over existing registry entries / metrics artifacts (reuse
`ExperimentRegistry.compare` semantics where possible).

### 4. P4.7b Robustness-Orchestrierung — #247 (delivered)

Wires the existing P5 helpers into orchestrated runs on the same
runner/registry/artifact line — no new backtester:

- `services/research/robustness.py` builds per-fold (walk-forward),
  per-scenario (cost stress), and per-neighbor (parameter stability) child
  `ExperimentSpec`s from a completed base run; bootstrap post-processes the
  base run's `equity.json` (no child runs, no second engine).
- `services/research/robustness_jobs.py` / `robustness_service.py` mirror the
  #242 job-store + in-process-thread pattern (`created→queued→running→completed|failed`).
- API under `/api/v1/research/robustness` (create/start/status/list/detail);
  each test's artifact (`artifacts/research/robustness/{robustness_id}/manifest.json`)
  is the intended gate-evaluator hook point for #248 (hook only, no gate
  persistence here).
- Minimal UI at `/dashboard/research/robustness` (create form, list, detail
  with per-child results and bootstrap quantiles) — synthetic/local-lab data
  only, no private Strategy V1 numbers.
- Tests: `tests/research/test_robustness_builders.py` (unit),
  `tests/research/test_robustness_api.py` (integration, local BTC fixture),
  `tests/dashboard/research-robustness.test.tsx` (UI smoke, synthetic fixtures).

### 5. P4.7c Versionierter Gate Evaluator und Gate-Persistenz — #248

Gate evaluation versioning, persistence of accept/reject reasons, no silent
promotion into paper trading.

### 6. P4.7d Validation Studies — #249

Validation studies API and UI.

### 7. P4.8 End-to-End-, Reproduzierbarkeits- und UI-Abnahmetests — #250

Playwright + API acceptance covering Lab → run → detail → compare; double-run
repro checks; no mock production data.

## Follow-up (not in #274)

**PostgresDatasetCatalog → Lab catalog:** Issue #274 ships file-based HL export
only (raw pages + versioned snapshot + `catalog.json`). Do **not** auto-list
`PostgresDatasetCatalog` in the Research write API and do not run
`import_from_raw_payload` as part of Lab publish. Track a dedicated follow-up
issue to optionally bridge Postgres-normalized datasets into the Lab catalog
(absolute/relative path rules, quality gate, R-015 snapshots) when product needs
it.

## Milestone note

Milestone remains **P4 – Research Engine und Research Workspace V1**.
P4 stays open until strategy is visible/selectable, research runs are possible
via UI, trade results are inspectable on charts, and full UI acceptance is done
(or explicitly deferred).
P5 stays blocked until Engine + Read-API + Workspace are jointly usable enough.
