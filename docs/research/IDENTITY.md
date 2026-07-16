# Experiment identity and RunManifest (P4-02 / #142)

## Identifiers

| ID | Derived from | Changes when |
|----|--------------|--------------|
| `experiment_id` | Semantic ExperimentSpec fields only | Semantic Spec change |
| `run_id` | Semantic Spec + git commit + dataset hash + strategy/cost/metrics/env versions | Code, dataset, or model/env pin change |
| `attempt_id` | Fresh UUID per physical execution | Every retry of the same `run_id` |

**Excluded from `experiment_id`:** `owner`, `notes`.

## RunManifest

- Schema version `1.0` (`services/research/schema/run_manifest.schema.json`)
- Written once to `run_manifest.json`; overwrite refused
- Invalidation must **not** mutate the file — use registry/sidecar (#145)

## CI double-run

Two executions of the same Spec on the same commit/dataset must share `run_id` and produce identical **semantic** artifact hashes. `attempt_id` and timestamps are excluded from semantic hashes.

Implemented by `research.repro.compare_semantic_run_dirs` and enforced in CI via `tests/research/test_double_run_repro.py` (job `research-repro`).
