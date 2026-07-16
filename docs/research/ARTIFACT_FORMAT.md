# Artifact format

Layout (Issue #143 / #49):

```text
artifacts/research/<experiment_id>/<run_id>/
  experiment.json
  run_manifest.json
  costs.json
  metrics.json
  report.md
  trades.json
  equity.json
  events.jsonl
  checksums.json
```

Registry index (append-only): `artifacts/research/registry.jsonl`  
Invalidation sidecars: `artifacts/research/invalidations/<run_id>.jsonl`

Rules:
- Write to a temporary directory, then move into place
- Refuse overwrite of an existing `(experiment_id, run_id)` directory
- Retries use a new `attempt_id` but do not replace successful artifacts
- `checksums.json` covers all files except itself
- Semantic CI compares (`#146`) hash metrics/trades/equity/costs/experiment plus manifest without `attempt_id` / `created_at_utc`
