# P4 Research Workspace — follow-up issues (Issue #240 / #242 / #265 / #266)

## Status (delivered / open)

**Delivered:** #265 — Trend Strategy V1 visible/selectable in Research (catalog + Lab). #266 — experiment detail **Kurs & Trades** chart from verified `trades.json` + run-bound `chart_data.json` candles (fail-closed integrity). #247 — Robustness-Orchestrierung (walk-forward, cost stress, parameter stability, bootstrap) auf derselben Runner/Registry/Artefakt-Linie + minimale UI unter `/dashboard/research/robustness` (siehe §4). #248 — Versionierter Gate Evaluator und Gate-Persistenz (Policy-Content-Hash-Bindung, evidenzgebundene, append-only Gate-Records, Read/Evaluate-API, keine Auto-Promotion; siehe §5).

#249 — Validation Studies API and UI, aggregating already-produced experiment/robustness/gate evidence (no second engine, no live/paper promotion). #250 — E2E/reproducibility/UI-acceptance suite implemented on `feat/250-research-e2e` (stacked on `main → #247 → #248 → #249`); see §7.

**Open:** #242 UI-Abnahme (Lab + catalog; manual checklist now documented, human run outstanding), #245 durable jobs, #246 compare (both off `main`, not on the #250 stack); Cancel/Retry deferred.

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

### 5. P4.7c Versionierter Gate Evaluator und Gate-Persistenz — #248 (delivered)

Evaluates evidence already produced by the research runner (#141-#147) and
the robustness orchestrator (#247) against a versioned, content-hash-bound
policy — no second backtest engine, no silent promotion into paper/live:

- `services/research/gate_policy.py` — versioned `GatePolicy` /
  `GateDefinition`; binding identity is the policy's SHA-256 content hash,
  not the version string alone (`verify_policy_content_hash` rejects a
  version silently re-defined with different content). Ships one generic
  example policy (`1.0`) — infrastructure for #249, not the private P5 human
  decision rules (`docs/research/p5/P5_DECISION_RULES.md`, #205).
- `services/research/gate_evaluator.py` — `GateEvaluator` binds evidence
  (run's sealed `RunManifest` + registry checksums + optional robustness
  manifests) into an immutable `GateRunRecord`: `run_id`, optional
  `robustness_run_ids`, `artifact_checksums`, `dataset_id` /
  `dataset_content_hash`, `policy_version` + `policy_content_hash`,
  `run_code_commit` + `evaluation_code_commit`. `GateResultStore` persists
  append-only under `artifacts/research/gates/registry.jsonl`
  (`registry.invalidate` pattern: invalidation appends a superseding record
  + sidecar, never rewrites).
- API under `/api/v1/research/gates` (`GET` list/detail, `POST /evaluate`,
  `POST /{gate_run_id}/invalidate`) + `GET /gate-policies`
  (`services/research/gate_service.py`, `services/research/api.py`).
- Tests: `tests/research/test_gate_policy.py` (content-hash + versioning
  unit tests, including the same-version-content-hash-mismatch case),
  `tests/research/test_gate_evaluator.py` (evidence binding, idempotent
  append-only persistence, invalidation), `tests/research/test_gate_api.py`
  (integration, local BTC fixture).
- Docs: `docs/research/GATES.md`.

### 6. P4.7d Validation Studies — #249

Validation studies API and UI.

### 7. P4.8 End-to-End-, Reproduzierbarkeits- und UI-Abnahmetests — #250 (implemented on `feat/250-research-e2e`)

API E2E acceptance (`tests/research/test_e2e_acceptance.py`) against the
committed `local_lab` catalog, without `RESEARCH_ALLOW_DIRTY_GIT`: canonical
strategy dedup, chart vs bound dataset + `trades.json`, tampered-checksum /
dataset-mismatch fail-closed with equity/drawdown proven unaffected,
deterministic failed job (no private data), Lab→Run→Detail happy path,
double-start blocked, and a robustness→gate→validation smoke chain. No
Playwright harness existed for research yet, so this stays API-level
(consistent with the existing vitest/pytest pattern for #265/#266); the repo's
only Playwright coverage remains the unrelated paper-trading dashboard specs
under `tests/visual/` and `tests/e2e/`. Compare (#246) and durable-job
restart/ownership (#245) are **not** on this branch stack (separate open PRs
off `main`) — their absence is asserted and documented, not silently skipped.
CLI compatibility guarded by `tests/research/test_cli_compat.py`. Manual UI
checklist: `docs/research/RESEARCH_WORKSPACE_ACCEPTANCE.md` (closes the
remaining #242 Abnahme theme; human execution/evidence still outstanding).

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
