# Research examples

## Local Strategy Lab catalog (dev fixture)

Committed under `examples/research/local_lab/`:

| File | Role |
|------|------|
| `catalog.json` | Dataset catalog for the Research write API |
| `bundle.json` | Fixture `HistoricalDataBundle` (BTC) |
| `dataset_manifest.json` | Matching P3 `DatasetManifest` |

**Fixture ≠ research:** the local BTC series is intentionally flat (~price 100)
for pipeline smoke tests. Trend V1 will show ~0 trades / flat equity on it. For
real Hyperliquid courses use the export CLI below (Issue #274).

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

## Hyperliquid → Lab catalog (Issue #274)

Ops CLI writes immutable raw HTTP pages, a versioned snapshot under
`<out-root>/<dataset_id>/`, and an atomic catalog alias (default
`hl-btc-mainnet-730d`). Identity is `dataset_id` / content hash — the alias is
only a Lab selector.

Offline / CI (no network, volatile synthetic pages):

```powershell
python scripts/export_research_dataset_hyperliquid.py `
  --end-date 2024-01-31 --days 31 --offline-synthetic `
  --code-commit <git-sha> `
  --out-root .\artifacts\research-datasets `
  --catalog-path .\artifacts\research-datasets\catalog.json
```

Default catalog alias is `hl-<symbol>-<network>-<days>d` (e.g. `hl-btc-mainnet-31d`).
Override with `--catalog-alias` only when intentional. Manifest `code_commit` must be a
real SHA (`--code-commit`, clean Git HEAD, or `RESEARCH_GIT_COMMIT` /
`RAILWAY_GIT_COMMIT_SHA`) — fail-closed otherwise.

Production (mainnet public API, pinned end date, absolute catalog paths):

```text
RESEARCH_REPO_ROOT=/app
RESEARCH_ARTIFACTS_ROOT=/data/research
RESEARCH_DATASET_CATALOG_PATH=/data/research/catalog.json
```

```bash
python scripts/export_research_dataset_hyperliquid.py \
  --end-date YYYY-MM-DD --days 730 \
  --out-root /data/research \
  --catalog-path /data/research/catalog.json
```

Requires `--end-date` or `--as-of` (no silent “today”). Same inputs →
byte-identical snapshot; quality gate must be VALID for D/W/M or export aborts
without catalog update. Postgres import is out of scope for this path.
