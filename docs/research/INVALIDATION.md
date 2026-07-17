# Invalidation

Historical research artifacts are immutable.

When a completed run must no longer count as valid evidence:

1. Set status `invalidated` in the **registry**
2. Append an **append-only sidecar** under `artifacts/research/invalidations/<run_id>.jsonl`
3. Record reason + provenance (actor/time)
4. Optionally reference a replacement `run_id`
5. **Do not** edit `run_manifest.json` or delete originals

CLI:

```bash
python -m research invalidate <run_id> --reason "..." --actor "<who>" [--replacement-run-id <id>]
```
