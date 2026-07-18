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

A `StudyRecord` stores **pinned** references, an immutable evidence snapshot,
and human-entered text — never private numbers:

| Field | Source |
|-------|--------|
| `experiment_id` / `run_id` | Resolved at create from the newest **complete** registry entry (failed / invalidated / non-complete rows are rejected); the exact `run_id` is persisted |
| `additional_experiment_ids` / `additional_run_ids` | Same complete-run pin contract, parallel lists |
| `robustness_ids` | Robustness test ids (#247); only `completed` jobs with a manifest are accepted; each manifest SHA-256 is snapshotted |
| `gate_run_ids` | Gate evaluation ids (#248); only `active` gates with a trusted policy content hash are accepted; each gate evidence content hash is snapshotted |
| `evidence_snapshot` | Immutable binding: run pins + checksum digests + dataset_id/content_hash + git commit + robustness manifest hashes + gate content hashes + `snapshot_id` |
| `strategy_id` / `strategy_version` | Read from the pinned base run's own artifacts |
| `decision` | Human-owned final decision bound to `evidence_snapshot_id`; `null` until recorded |

Creation fails closed (`422`) if any referenced id does not already exist as
acceptable evidence — a Study can only ever point at evidence that was already
produced elsewhere, and never at a failed/invalidated run.

## Evidence snapshot (immutable binding)

On create the service builds a `StudyEvidenceSnapshot` and persists it on the
study record. **Reads hydrate from that snapshot**, not from whatever the
registry currently lists as the latest entry for an `experiment_id`. If a
newer complete run B is registered later for the same experiment, an existing
study that pinned run A continues to return run A.

Verification:

- Open studies: snapshot is re-checked on read; mismatches surface as
  `evidence_integrity: { ok: false, error, snapshot_id }` while still
  returning the pinned (not live-latest) evidence.
- Decided studies: snapshot re-verification **fails closed** (`409`) when
  underlying evidence was invalidated or checksums / hashes no longer match.

## Final decision (human-owned, never automatic)

`POST /validation/{study_id}/decision` records exactly one
`{outcome: "accept" | "reject" | "inconclusive", rationale, decided_by}`.
This mirrors the generic P5 decision vocabulary
(`docs/research/p5/P5_DECISION_RULES.md`) without binding this
infrastructure to the private Strategy V1 decision itself — #205 remains
the canonical, human-signed-off decision for Strategy V1.

Before accepting a decision the service **re-verifies** the immutable
evidence snapshot and stores `decision.evidence_snapshot_id`. A decision is
rejected if the snapshot cannot be re-verified. The decision is **never**
inferred from a gate's `overall_status` and **never** a promotion trigger:
no code path here calls into `paper_trading` or any live order surface.
Persistence is append-only, mirroring `GateResultStore` (#248): a decided
Study is never mutated or re-decided — new evidence requires a new Study
(`AGENTS.md` §8, never overwrite historical research).

## API

`services/research/api.py` (`/api/v1/research/...`):

| Route | Purpose |
|-------|---------|
| `GET /validation` | List studies (optional `?experiment_id=` / `?status=`) |
| `POST /validation` | Create a study (idempotent on the same pinned evidence set) |
| `GET /validation/{study_id}` | One hydrated study (snapshot-pinned; decided studies fail closed on integrity loss) |
| `POST /validation/{study_id}/decision` | Append-only, one-shot final decision bound to `snapshot_id` |

## Dashboard

- `/dashboard/research/validation` — create form + studies table
- `/dashboard/research/validation/[studyId]` — full detail view (strategy
  and version, study status, progress, involved experiments, walk-forward /
  cost-stress / parameter-stability / bootstrap sections, gate results,
  final decision, policy version, reproducibility fields) + decision form
  while the study is still open

## Tests

- `tests/research/test_validation_study.py` — deterministic `study_id`,
  append-only persistence, one-shot decision, snapshot-id binding.
- `tests/research/test_validation_api.py` — integration (local BTC
  fixture): create/list/get, idempotency, unknown-reference rejection,
  pin stability across later complete runs, reject create on
  failed/invalidated runs, decision snapshot binding, decided-study
  fail-closed after invalidation (`409`), double-decide rejection (`409`).
- `tests/dashboard/research-validation.test.tsx` — static-render component
  tests, including a leakage-negative assertion that no promotion/live
  affordance is ever rendered for a study decision.
