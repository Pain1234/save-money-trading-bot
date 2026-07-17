# Research examples

## Local Strategy Lab catalog (dev)

Committed under `examples/research/local_lab/`:

| File | Role |
|------|------|
| `catalog.json` | Dataset catalog for the Research write API |
| `bundle.json` | Fixture `HistoricalDataBundle` (BTC) |
| `dataset_manifest.json` | Matching P3 `DatasetManifest` |

Regenerate (deterministic `created_at`; safe to re-run without dirtying provenance metadata):

```powershell
python scripts/prepare_research_lab_local.py
```

If `RESEARCH_DATASET_CATALOG_PATH` / `RESEARCH_DATASET_CATALOG_JSON` are unset,
the API loads this catalog automatically when the file exists (Issue #264).

Recommended local API env (API process, not only Next.js):

```powershell
$env:RESEARCH_REPO_ROOT = "<repo-root>"
$env:RESEARCH_ARTIFACTS_ROOT = "<repo-root>"
# optional explicit catalog:
$env:RESEARCH_DATASET_CATALOG_PATH = "<repo-root>\examples\research\local_lab\catalog.json"
```

Keep the git working tree **clean** so research runs record real HEAD provenance.
`RESEARCH_ALLOW_DIRTY_GIT=1` is a documented exception for tests / explicit local
overrides only — print it with:

```powershell
python scripts/prepare_research_lab_local.py --print-env-only --print-dirty-git-exception
```

With `RESEARCH_ARTIFACTS_ROOT` pointing at the repo root, registry and jobs land
under gitignored `artifacts/research/`. An empty Experiments list means no runs
yet — use **Neues Experiment** after the catalog is available.

Lab day bounds use inclusive whole seconds (`…T23:59:59.000000Z`), matching this
fixture’s manifest end (not `.999999Z`).
