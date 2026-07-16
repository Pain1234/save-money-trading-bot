# Reproducibility

- Same semantic Spec → same `experiment_id`
- Same Spec + git commit + dataset hash + model/env pins → same `run_id`
- Owner/notes excluded from identity
- CI double-run compares **semantic** hashes (excludes `attempt_id`, timestamps)
- Offline only: research runs must not require live exchange network
- Cost stress / OOS evaluation is **P5**, not required for P4 reproducibility
