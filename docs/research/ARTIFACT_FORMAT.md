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
  chart_data.json
  regime_labels.json
  regime_metrics.json
  confidence_profile.json
  behavior_profile.json
  parameter_area.json
  events.jsonl
  checksums.json
```

Registry index (append-only): `artifacts/research/registry.jsonl`  
Invalidation sidecars: `artifacts/research/invalidations/<run_id>.jsonl`

Optional sibling store for standalone classifier seals (#285):

```text
artifacts/research/regimes/<classification_id>/
  regime_labels.json
  regime_labels.json.sha256
```

Rules:
- Write to a temporary directory, then move into place
- Refuse overwrite of an existing `(experiment_id, run_id)` directory
- Retries use a new `attempt_id` but do not replace successful artifacts
- `checksums.json` covers all files except itself (convenience seal in the run directory)
- **Trust anchor (#165):** on `register_complete` / `show(verify=True)`, file digests are checked against the **checksum snapshot stored in the registry entry**, not solely by re-reading mutable `checksums.json`. Tamper + reseal of `checksums.json` alone must fail verification.
- Semantic CI compares (`#146`) hash metrics/trades/equity/costs/experiment/chart_data/regime_labels/regime_metrics/behavior_profile plus manifest without `attempt_id` / `created_at_utc`
- Registry CLI `compare` (`#167`) diffs full `semantic_spec_dict` + `semantic_manifest_payload` (see [README.md](README.md))
- `regime_labels.json` (#285): versioned classifier labels + transitions; see [REGIME_CLASSIFIER.md](REGIME_CLASSIFIER.md)
- `regime_metrics.json` (#287): per-regime raw quality metrics; see [REGIME_QUALITY.md](REGIME_QUALITY.md)
- `confidence_profile.json` (#288): evidence-confidence profile; see [CONFIDENCE.md](CONFIDENCE.md)
- Scorecard aggregate store (#291): `artifacts/research/scorecards/registry.jsonl`
  (+ invalidation sidecars); see [SCORECARDS.md](SCORECARDS.md) — not a second
  experiment registry; not written into the run directory
- `behavior_profile.json` (#289): deterministic behaviour + transition risk; see [REGIME_BEHAVIOUR.md](REGIME_BEHAVIOUR.md)
- `parameter_area.json` (#290): optional post-hoc plateau classification from #247; see [PARAMETER_AREA.md](PARAMETER_AREA.md)
