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

## Registry compare (#167)

CLI `python -m research compare <run_a> <run_b>` is a **semantic compatibility** check, not a byte-equality gate:

1. Load and validate `experiment.json` → `semantic_spec_dict` (owner/notes excluded).
2. Load and validate `run_manifest.json` → `semantic_manifest_payload` (no attempt/timestamp).
3. Emit per-key diffs (`spec.*`, `manifest.*`) plus registry status fields.
4. Compatible only if both entries are `complete` and diffs are empty.

This catches divergent symbols, windows, capital, fee/slippage/funding rates, seeds, and cost scenarios that a shallow version-only compare would miss.

## Archive / immutability

Do not edit sealed run directories in place. Correct with a new run (new attempt or new Spec → new ids) and optionally `invalidate` the old `run_id` via registry/sidecar ([INVALIDATION.md](INVALIDATION.md)).
