# Artifact format

Layout (Issue #143):

```text
artifacts/research/<experiment_id>/<run_id>/
  experiment.json
  run_manifest.json
  metrics.json
  report.md
  trades.json
  equity.json
  events.jsonl
  checksums.json
```

Rules:
- Write to a temporary directory, then move into place
- Refuse overwrite of an existing `(experiment_id, run_id)` directory
- Retries use a new `attempt_id` but do not replace successful artifacts
- `checksums.json` covers all files except itself
