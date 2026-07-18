# P4 Research Workspace — follow-up issues (Issue #240 / #242 / #265 / #266)

## Status (delivered / open)

**Delivered:** #265 — Trend Strategy V1 visible/selectable in Research (catalog + Lab). #266 — experiment detail **Kurs & Trades** chart from verified `trades.json` + run-bound `chart_data.json` candles (fail-closed integrity). #247 — Robustness-Orchestrierung (walk-forward, cost stress, parameter stability, bootstrap) auf derselben Runner/Registry/Artefakt-Linie + minimale UI unter `/dashboard/research/robustness` (siehe §4).

**Open:** #242 UI-Abnahme (Lab + catalog), #245 durable jobs, #246/#248/#249 compare/gates/validation, #250 E2E/UI acceptance; Cancel/Retry deferred.

## Recommended issue split

### 1–2. P4.6 Strategy Lab + Async Runs — done in #242 / PR #243

Combined vertical slice: Strategy Lab UI, write API, filesystem job store,
in-process worker wrapping `run_experiment`, status polling.

**V1 job limit (superseded by #245):** the original #242/#243 slice used
in-process threads that did not resume after an API process restart; stale
`running` jobs were failed closed on the next status read. Issue #245
replaces this with a durable, cross-process-safe ownership contract — see
below.

**Abnahme:** #242 remains open until manual UI acceptance with a dataset catalog
(also covered by #250). Local catalog helper tracked separately (#264).

### 1b. P4.6b Durable Research Job Execution und Restart Recovery — #245

Filesystem job store still has no Celery/Redis mandate, but process-local
locks/CAS alone are not sufficient once more than one API process can touch
the same job store (e.g. multiple Railway/uvicorn workers). #245 adds an
explicit cross-process ownership contract on top of the existing
`ResearchJobStore` / `ResearchWriteService`:

- `worker_id` — stable identity of a process/worker instance (one UUID
  generated once per process import, not derived from a potentially reused
  PID).
- `lease_id` — unique per claim attempt (fresh UUID each time a job is
  claimed `queued -> running`); kept distinct from the pre-existing
  `attempt_id` field, which identifies the run-manifest attempt produced by
  the backtest engine, not job ownership.
- **Cross-process atomic claim:** `ResearchJobStore.claim()` wraps the
  `queued -> running` read-modify-write in an interprocess file lock
  (`msvcrt.locking` on Windows, `fcntl.flock` on POSIX) in addition to the
  existing process-local `threading.RLock`, so two processes racing to claim
  the same job get exactly one winner.
- **Lease renewal:** the owning worker thread renews `lease_expires_at` on a
  heartbeat interval (`RESEARCH_JOB_LEASE_SECONDS` / `RESEARCH_JOB_LEASE_HEARTBEAT_SECONDS`)
  while the run is in progress.
- **Conditional terminal write:** `ResearchJobStore.finish()` only applies a
  `completed` / `failed` write if the caller still owns the job's current
  `worker_id` + `lease_id`, and never overwrites an already-terminal job — a
  stale/former owner cannot resurrect or overwrite a job it no longer owns.

**Restart semantics:**

| Status at restart | Behavior |
|---|---|
| `created` | unchanged |
| `queued`, no live owner | re-dispatched by the startup recovery hook (`ResearchJobStore.recover_orphans` / `ResearchWriteService.recover_orphans`) |
| `running`, dead lease | failed closed with a clear reason — **no mid-run resume** |
| `running`, live lease (owned by a still-alive worker, possibly in another process) | left untouched |
| terminal (`completed` / `failed`) | unchanged |

The recovery hook runs once at API startup (paper-trading read-only API
lifespan, `services/paper_trading/readonly_api.py`), before the API starts
serving research-write traffic. No Celery/Redis is introduced; Cancel/Retry/
Re-run remain out of scope (unchanged, deferred).

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
