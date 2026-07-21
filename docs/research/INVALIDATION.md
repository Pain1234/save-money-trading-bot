# Invalidation

Historical research artifacts are immutable.

When a completed run must no longer count as valid evidence:

1. Set status `invalidated` in the **registry**
2. Append an **append-only sidecar** under `artifacts/research/invalidations/<run_id>.jsonl`
3. Record reason + provenance (actor/time)
4. Optionally reference a replacement `run_id`
5. **Do not** edit `run_manifest.json` or delete originals

The sidecar is the binding authority on every registry read and artifact
reconstruction. While it exists, later `complete`/`failed` JSONL records cannot
reactivate the run, and append APIs reject such records. Empty, malformed, or
unreadable sidecars fail closed as invalidated. Registry-backed consumers
(including the Research API and new robustness, gate, scorecard, or validation
evaluation) therefore resolve the run as invalidated even if `registry.jsonl` is
stale or rebuilt from immutable artifacts.

Existing persisted gate, scorecard, robustness, and validation records remain
immutable and are not automatically invalidated by this registry sidecar. When
the source-run defect affects their evidence, assess and invalidate those
downstream records through their own append-only invalidation workflows.

CLI:

```bash
python -m research invalidate <run_id> --reason "..." --actor "<who>" [--replacement-run-id <id>]
```
