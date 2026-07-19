# Scorecards (Issue #291 / P4.9 Layer 5)

Assembles pinned layer artifacts into a **global evidence profile** and persists
an append-only scorecard record. No second experiment/gate registry. No
re-backtest. No auto-promotion.

Contract: [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) § Layer 5 / §8.
Related: [`GATES.md`](GATES.md), [`CONFIDENCE.md`](CONFIDENCE.md),
[`VALIDATION_STUDIES.md`](VALIDATION_STUDIES.md).

## Persistenz

Append-only JSONL (mirrors gates):

```text
artifacts/research/scorecards/registry.jsonl
artifacts/research/scorecards/invalidations/<scorecard_id>.jsonl
```

Scorecards are **not** written into the immutable run directory (run dirs already
hold layer sidecars). Invalidation supersedes; originals are never rewritten.

## Deterministic `scorecard_id`

`sc_{sha256}` over:

- `run_id`, optional `gate_run_id`, sorted `robustness_run_ids`
- sealed `robustness_manifest_hashes` (id → #247 manifest content hash)
- scorecard `policy_version` + `policy_content_hash`
- `dataset_id` + `dataset_content_hash`
- `layer_refs` (classification/quality/behaviour/confidence/parameter_area pins)

Re-evaluating the same **active** evidence under the same policy is idempotent.
If the same `scorecard_id` was **invalidated**, evaluate fails closed (no silent
reactivation without new evidence / policy).

## Evidence seal

Each record persists `evidence_content_hash` over immutable fields (profile,
layer refs, limitations, commits, promotion flags, checksums, … — not status /
`evaluated_at`). Reads and ValidationStudy pins recompute and compare; tampering
the JSONL record fails closed.

Optional `robustness_run_ids` are verified via the same #247 path as gates
(completed job, `base_run_id`, sealed manifest hash) and stored under
`artifact_checksums["robustness/{id}/manifest.json"]`. Optional gates also run
`verify_policy_content_hash`.

## Required / optional layers (policy 1.0)

| Layer file | Role |
|------------|------|
| `regime_labels.json` | required |
| `regime_metrics.json` | required |
| `behavior_profile.json` | required |
| `confidence_profile.json` | optional — if missing, derived at evaluate time (not written back) |
| `parameter_area.json` | optional — if missing → `NOT_AVAILABLE` (#290) |

## API

| Route | Notes |
|-------|-------|
| `GET /api/v1/research/scorecard-policies` | versions + content hash |
| `GET /api/v1/research/scorecards?run_id=` | latest-per-id |
| `GET /api/v1/research/scorecards/{scorecard_id}` | fail-closed integrity for active |
| `POST /api/v1/research/scorecards/evaluate` | idempotent assemble |
| `POST /api/v1/research/scorecards/{id}/invalidate` | append-only |

`promotion_action` / `auto_promotion` / `decision_binding` are always false/`none`.

## Validation Study pin (#249 extension)

Studies (schema `1.2`) accept optional `scorecard_ids`. Each active scorecard is
pinned by `scorecard_evidence_content_hash` into `evidence_snapshot.scorecards`.
Decided studies re-verify pins fail-closed.

## Policy hash

`SCORECARD_POLICY_1_0_CONTENT_HASH` in `scorecard_policy.py` (literal regression pin).

## Acceptance / anti-overfit (#293)

Composition matrix (no dashboard UI):

```text
python -m pytest tests/research/test_scorecard_e2e_acceptance.py -q
```

Covers: same inputs → same `scorecard_id`, evidence tamper fail-closed, bound
critical gate FAIL preserved, invalidation without reactivation, policy content
hash under same version string, parameter-area isolated vs broad, Sideways
defensive inactivity. Auto-promotion flags remain false/`none`.
