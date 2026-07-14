# P3 Dataset Reproducibility Audit

**Issue:** #84  
**Epic:** #45 (R-001)  
**Date:** 2026-07-14

## ROADMAP P3 exit criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Each research dataset has manifest (hash, range, symbols, source) | Pass | `DatasetManifest` (#77), import pipeline (#80), example in `tests/market_data/fixtures/` |
| Re-import produces identical aggregates for fixed version | Pass | `test_historical_import.py`, `test_aggregation_manifest.py` |
| Gap/duplicate audit documented | Pass | `dataset_quality.py` (#81), `test_dataset_quality.py` |

## R-001 acceptance (#45)

| Requirement | Issue | Evidence |
|-------------|-------|----------|
| Dataset-ID | #77 | `derive_dataset_id()` |
| Manifest fields | #77 | `manifest.py` |
| Gap/duplicate detection | #81 | `evaluate_dataset_quality()` |
| Stale threshold | #81 | `is_candle_data_stale()` in quality path |
| Quarantine | #82 | `require_research_dataset()` |
| Re-import identical aggregates | #80, #83 | import + derived hash tests |
| Regression tests | #76–#83 | `pytest tests/market_data -m "not live"` |

## Determinism evidence

```text
immutable raw artifact + import config + code commit -> normalized content_hash
```

Verified by:

- `tests/market_data/test_historical_import.py::test_import_from_fixture_is_deterministic`
- `tests/market_data/test_aggregation_manifest.py::test_aggregation_deterministic`

## Quarantine evidence

- `tests/market_data/test_quarantine.py::test_quarantine_blocks_invalid_dataset`

## Test command

```bash
python -m pytest tests/market_data -m "not live" -q
```

## Storage / backup notes (ADR-013)

- Catalog: PostgreSQL migration `010_market_data_datasets`
- Raw artifacts: `MARKET_DATA_DATASET_ROOT` filesystem path
- Paper-trading tables unchanged

## Open items (non-P3 blockers)

- Railway non-prod restore (#11) — does not block P3 per ADR-012
- Research experiment binding to `dataset_id` — P4
