# Validation Studies (Issue #249 / P4.7d)

Aggregates already-produced research evidence — completed experiments/runs
(#141-#147, #242), robustness manifests (#247) and versioned gate evaluation
records (#248) — into one reviewable unit. **No second backtest engine, no
gate re-evaluation, no live/paper promotion anywhere in this surface.**

This is generic P4.7d infrastructure. It does **not** implement the private
Strategy V1 study registration with real results (#255) or the final P5
decision (#205); public fixtures/examples must stay synthetic/generic
(#181).

## What a Study binds

A `StudyRecord` only stores references and human-entered text — never
private numbers:

| Field | Source |
|-------|--------|
| `experiment_id` / `run_id` | Resolved from the registry (never trusts client-supplied strategy metadata) |
| `additional_experiment_ids` | Other experiment ids included in the study, each verified against the registry |
| `robustness_ids` | Robustness test ids (#247), each verified against the robustness job store |
| `gate_run_ids` | Gate evaluation ids (#248), each verified against the gate result store |
| `strategy_id` / `strategy_version` | Read from the base experiment's own artifacts |
| `decision` | Human-owned final decision (see below); `null` until recorded |

Creation fails closed (`422`) if any referenced id does not already exist —
a Study can only ever point at evidence that was already produced
elsewhere.

## Hydration (read-only aggregation)

`GET /validation/{study_id}` (and each list item) resolves every reference
live, through the existing services — `ResearchReadService`,
`RobustnessOrchestrationService`, `GateService` — rather than storing a
snapshot that could drift or duplicate private numbers:

- `experiments`: resolved experiment summaries (status, net PnL, drawdown, …)
- `robustness` / `robustness_by_type`: resolved robustness job status +
  manifest, grouped by `walk_forward` / `cost_stress` /
  `parameter_stability` / `bootstrap` (#247)
- `gates`: resolved `GateRunRecord`s (#248), always carrying
  `promotion_action: "none"`
- `progress`: counts of complete/failed/running across the above
- `reproducibility`: `git_commit`, `evaluation_code_commit`, `dataset_id`,
  `dataset_content_hash`, `policy_version` + `policy_content_hash` — taken
  from the most recently evaluated bound gate record when present (the gate
  already carries the sealed evidence-binding contract), else from the base
  experiment's own artifacts

## Final decision (human-owned, never automatic)

`POST /validation/{study_id}/decision` records exactly one
`{outcome: "accept" | "reject" | "inconclusive", rationale, decided_by}`.
This mirrors the generic P5 decision vocabulary
(`docs/research/p5/P5_DECISION_RULES.md`) without binding this
infrastructure to the private Strategy V1 decision itself — #205 remains
the canonical, human-signed-off decision for Strategy V1.

The decision is **never** inferred from a gate's `overall_status` and
**never** a promotion trigger: no code path here calls into `paper_trading`
or any live order surface. Persistence is append-only, mirroring
`GateResultStore` (#248): a decided Study is never mutated or re-decided —
new evidence requires a new Study (`AGENTS.md` §8, never overwrite
historical research).

## API

`services/research/api.py` (`/api/v1/research/...`):

| Route | Purpose |
|-------|---------|
| `GET /validation` | List studies (optional `?experiment_id=` / `?status=`) |
| `POST /validation` | Create a study (idempotent on the same reference set) |
| `GET /validation/{study_id}` | One hydrated study |
| `POST /validation/{study_id}/decision` | Append-only, one-shot final decision |

## Dashboard

- `/dashboard/research/validation` — create form + studies table
- `/dashboard/research/validation/[studyId]` — full detail view (strategy
  and version, study status, progress, involved experiments, walk-forward /
  cost-stress / parameter-stability / bootstrap sections, gate results,
  final decision, policy version, reproducibility fields) + decision form
  while the study is still open

## Tests

- `tests/research/test_validation_study.py` — deterministic `study_id`,
  append-only persistence, one-shot decision.
- `tests/research/test_validation_api.py` — integration (local BTC
  fixture): create/list/get, idempotency, unknown-reference rejection,
  decision recording, double-decide rejection (`409`).
- `tests/dashboard/research-validation.test.tsx` — static-render component
  tests, including a leakage-negative assertion that no promotion/live
  affordance is ever rendered for a study decision.
