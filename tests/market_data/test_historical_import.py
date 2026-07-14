"""Tests for historical import (#80)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from market_data.content_hash import hash_normalized_candles
from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.historical_import import (
    HistoricalImportConfig,
    _parse_hyperliquid_snapshot,
    import_from_raw_payload,
    renormalize_from_raw_hash,
    resume_import_from_checkpoint,
)
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.normalize import normalize_batch
from market_data.raw_store import FileRawArtifactStore

FIXTURE = Path(__file__).parent / "fixtures" / "hyperliquid_daily_snapshot.json"
EVAL_TIME = datetime(2026, 1, 15, tzinfo=UTC)


def _config() -> HistoricalImportConfig:
    return HistoricalImportConfig(
        source="hyperliquid/mainnet",
        symbol=MarketSymbol.BTC,
        timeframe=MarketTimeframe.DAILY,
        code_commit="abc1234",
        import_configuration={"fixture": True},
    )


def test_import_from_fixture_is_deterministic(tmp_path: Path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    payload = FIXTURE.read_bytes()
    config = _config()
    first = import_from_raw_payload(
        catalog, store, payload, config, evaluation_time=EVAL_TIME
    )
    raws = _parse_hyperliquid_snapshot(payload, config, EVAL_TIME)
    normalized = normalize_batch(raws, EVAL_TIME)
    assert hash_normalized_candles(normalized) == first.manifest.content_hash
    assert first.candles_imported == 2
    reloaded = store.load(first.raw_content_hash)
    assert reloaded == payload


def test_renormalize_is_idempotent_on_existing_dataset(tmp_path: Path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    payload = FIXTURE.read_bytes()
    config = _config()
    first = import_from_raw_payload(
        catalog, store, payload, config, evaluation_time=EVAL_TIME
    )
    second = renormalize_from_raw_hash(
        catalog,
        store,
        first.raw_content_hash,
        config,
        evaluation_time=EVAL_TIME,
    )
    assert second.manifest.dataset_id == first.manifest.dataset_id
    assert second.manifest.content_hash == first.manifest.content_hash


def test_renormalize_without_evaluation_time_is_deterministic(tmp_path: Path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    payload = FIXTURE.read_bytes()
    config = _config()
    first = import_from_raw_payload(catalog, store, payload, config)
    second = renormalize_from_raw_hash(
        catalog,
        store,
        first.raw_content_hash,
        config,
    )
    assert second.manifest.dataset_id == first.manifest.dataset_id
    assert second.manifest.content_hash == first.manifest.content_hash


def test_identical_payloads_get_distinct_raw_dataset_ids(tmp_path: Path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    payload = FIXTURE.read_bytes()
    config = _config()
    import_from_raw_payload(
        catalog, store, payload, config, evaluation_time=EVAL_TIME
    )
    import_from_raw_payload(
        catalog, store, payload, config, evaluation_time=EVAL_TIME
    )
    assert len(catalog._raw) == 2
    raw_ids = {record.raw_dataset_id for record in catalog._raw.values()}
    assert len(raw_ids) == 2


def test_import_checkpoint_resume(tmp_path: Path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    payload = FIXTURE.read_bytes()
    config = _config()
    checkpoint_dir = tmp_path / "checkpoints"
    job_id = "job-001"
    first = import_from_raw_payload(
        catalog,
        store,
        payload,
        config,
        evaluation_time=EVAL_TIME,
        checkpoint_dir=checkpoint_dir,
        job_id=job_id,
    )
    resumed = resume_import_from_checkpoint(
        catalog,
        store,
        config,
        checkpoint_dir,
        job_id,
        evaluation_time=EVAL_TIME,
    )
    assert resumed.manifest.dataset_id == first.manifest.dataset_id
