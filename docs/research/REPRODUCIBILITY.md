# Reproducibility

- Same semantic Spec → same `experiment_id`
- Same Spec + git commit + dataset hash + model/env pins → same `run_id`
- Owner/notes excluded from identity
- CI double-run compares **semantic** hashes (excludes `attempt_id`, timestamps)
- Offline only: research runs must not require live exchange network
- Cost stress / OOS evaluation is **P5**, not required for P4 reproducibility

## Mechanical gate (#146)

The `research-repro` CI job runs `tests/research/test_double_run_repro.py`:

1. Execute the same Spec + bundle twice with **different** `artifacts_root` paths.
2. Assert shared `run_id` and distinct `attempt_id`.
3. Compare semantic hashes of `metrics.json`, `trades.json`, `equity.json`, `costs.json`, `experiment.json`, and `run_manifest.json` (manifest without `attempt_id` / `created_at_utc`).
4. Same-root second run must fail closed on overwrite protection.

Helper: `research.repro.compare_semantic_run_dirs`.
