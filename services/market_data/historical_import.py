"""Deterministic historical import from immutable raw artifacts (#80)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from market_data.content_hash import derive_dataset_id, hash_normalized_candles
from market_data.dataset_catalog import DatasetCatalog, DatasetCatalogError
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.normalize import normalize_batch
from market_data.providers.hyperliquid import (
    HyperliquidCandleAdapter,
    coin_for_symbol,
    interval_for_timeframe,
)
from market_data.raw_store import FileRawArtifactStore, RawArtifactRecord


@dataclass(frozen=True)
class HistoricalImportConfig:
    source: str
    symbol: MarketSymbol
    timeframe: MarketTimeframe
    code_commit: str
    import_configuration: dict[str, Any]
    endpoint: str = "https://api.hyperliquid.xyz/info"


@dataclass(frozen=True)
class HistoricalImportResult:
    manifest: DatasetManifest
    candles_imported: int
    raw_content_hash: str


@dataclass(frozen=True)
class ImportCheckpoint:
    job_id: str
    phase: str
    raw_content_hash: str | None = None
    raw_dataset_id: str | None = None
    dataset_id: str | None = None


def _checkpoint_path(checkpoint_dir: Path, job_id: str) -> Path:
    return checkpoint_dir / f"{job_id}.json"


def save_import_checkpoint(checkpoint_dir: Path, checkpoint: ImportCheckpoint) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": checkpoint.job_id,
        "phase": checkpoint.phase,
        "raw_content_hash": checkpoint.raw_content_hash,
        "raw_dataset_id": checkpoint.raw_dataset_id,
        "dataset_id": checkpoint.dataset_id,
    }
    _checkpoint_path(checkpoint_dir, checkpoint.job_id).write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def load_import_checkpoint(checkpoint_dir: Path, job_id: str) -> ImportCheckpoint | None:
    path = _checkpoint_path(checkpoint_dir, job_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ImportCheckpoint(
        job_id=data["job_id"],
        phase=data["phase"],
        raw_content_hash=data.get("raw_content_hash"),
        raw_dataset_id=data.get("raw_dataset_id"),
        dataset_id=data.get("dataset_id"),
    )


def _parse_hyperliquid_snapshot(
    payload: bytes,
    config: HistoricalImportConfig,
    evaluation_time: datetime,
) -> tuple[Any, ...]:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, list):
        msg = "expected JSON array of candles"
        raise ValueError(msg)
    adapter = HyperliquidCandleAdapter()
    coin = coin_for_symbol(config.symbol)
    interval = interval_for_timeframe(config.timeframe)
    raws = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raws.append(
            adapter.parse_candle(
                item,
                expected_coin=coin,
                expected_interval=interval,
                evaluation_time=evaluation_time,
                strict=False,
            )
        )
    return tuple(raws)


def _build_manifest(
    config: HistoricalImportConfig,
    normalized: tuple,
    record: RawArtifactRecord,
    evaluation_time: datetime,
) -> DatasetManifest:
    content_hash = hash_normalized_candles(normalized)
    start = min(c.open_time for c in normalized)
    end = max(c.close_time for c in normalized)
    return DatasetManifest(
        source=config.source,
        symbols=(config.symbol,),
        timeframes=(config.timeframe,),
        start_timestamp=start,
        end_timestamp=end,
        row_count=len(normalized),
        content_hash=content_hash,
        raw_dataset_id=record.raw_dataset_id,
        raw_content_hash=record.content_hash,
        import_configuration=config.import_configuration,
        code_commit=config.code_commit,
        created_at=evaluation_time,
    )


def _existing_published_result(
    catalog: DatasetCatalog,
    dataset_id: str,
    raw_content_hash: str,
) -> HistoricalImportResult | None:
    try:
        manifest = catalog.get_manifest(dataset_id)
    except DatasetCatalogError:
        return None
    candles = catalog.list_candles(dataset_id)
    return HistoricalImportResult(
        manifest=manifest,
        candles_imported=len(candles),
        raw_content_hash=raw_content_hash,
    )


def import_from_raw_payload(
    catalog: DatasetCatalog,
    raw_store: FileRawArtifactStore,
    payload: bytes,
    config: HistoricalImportConfig,
    *,
    evaluation_time: datetime | None = None,
    checkpoint_dir: Path | None = None,
    job_id: str | None = None,
    raw_record: RawArtifactRecord | None = None,
) -> HistoricalImportResult:
    """Capture raw bytes, normalize deterministically, publish dataset."""
    evaluation_time = evaluation_time or datetime.now(tz=UTC)
    if checkpoint_dir and job_id:
        existing = load_import_checkpoint(checkpoint_dir, job_id)
        if existing and existing.phase == "published" and existing.dataset_id:
            cached = _existing_published_result(
                catalog,
                existing.dataset_id,
                existing.raw_content_hash or hash_normalized_candles(()),
            )
            if cached is not None:
                return cached

    if raw_record is None:
        fetch_metadata = {
            "endpoint": config.endpoint,
            "symbol": config.symbol.value,
            "timeframe": config.timeframe.value,
            **config.import_configuration,
        }
        record = raw_store.store(
            payload,
            source=config.source,
            fetch_metadata=fetch_metadata,
            fetch_id=raw_store.new_fetch_id(),
        )
        catalog.register_raw_artifact(record)
        if checkpoint_dir and job_id:
            save_import_checkpoint(
                checkpoint_dir,
                ImportCheckpoint(
                    job_id=job_id,
                    phase="raw_stored",
                    raw_content_hash=record.content_hash,
                    raw_dataset_id=record.raw_dataset_id,
                ),
            )
    else:
        record = raw_record

    raws = _parse_hyperliquid_snapshot(payload, config, evaluation_time)
    normalized = normalize_batch(raws, evaluation_time)
    if not normalized:
        msg = "no candles parsed from raw payload"
        raise ValueError(msg)

    content_hash = hash_normalized_candles(normalized)
    dataset_id = derive_dataset_id(content_hash, "1.0", config.source)
    cached = _existing_published_result(catalog, dataset_id, record.content_hash)
    if cached is not None:
        if checkpoint_dir and job_id:
            save_import_checkpoint(
                checkpoint_dir,
                ImportCheckpoint(
                    job_id=job_id,
                    phase="published",
                    raw_content_hash=record.content_hash,
                    raw_dataset_id=record.raw_dataset_id,
                    dataset_id=dataset_id,
                ),
            )
        return cached

    manifest = _build_manifest(config, normalized, record, evaluation_time)
    published = catalog.publish_dataset(manifest)
    assert published.dataset_id is not None
    added = catalog.append_candles(published.dataset_id, normalized)
    if checkpoint_dir and job_id:
        save_import_checkpoint(
            checkpoint_dir,
            ImportCheckpoint(
                job_id=job_id,
                phase="published",
                raw_content_hash=record.content_hash,
                raw_dataset_id=record.raw_dataset_id,
                dataset_id=published.dataset_id,
            ),
        )
    return HistoricalImportResult(
        manifest=published,
        candles_imported=added,
        raw_content_hash=record.content_hash,
    )


def renormalize_from_raw_hash(
    catalog: DatasetCatalog,
    raw_store: FileRawArtifactStore,
    raw_content_hash: str,
    config: HistoricalImportConfig,
    *,
    evaluation_time: datetime | None = None,
) -> HistoricalImportResult:
    """Re-normalize from stored raw artifact (determinism check)."""
    evaluation_time = evaluation_time or datetime.now(tz=UTC)
    payload = raw_store.load(raw_content_hash)
    raws = _parse_hyperliquid_snapshot(payload, config, evaluation_time)
    normalized = normalize_batch(raws, evaluation_time)
    if not normalized:
        msg = "no candles parsed from raw payload"
        raise ValueError(msg)
    content_hash = hash_normalized_candles(normalized)
    dataset_id = derive_dataset_id(content_hash, "1.0", config.source)
    cached = _existing_published_result(catalog, dataset_id, raw_content_hash)
    if cached is not None:
        return cached

    record = RawArtifactRecord(
        raw_dataset_id=raw_store.new_fetch_id(),
        content_hash=raw_content_hash,
        storage_relpath=f"raw/{raw_content_hash}.json",
        source=config.source,
        fetch_metadata={"renormalize": True, **config.import_configuration},
    )
    catalog.register_raw_artifact(record)
    return import_from_raw_payload(
        catalog,
        raw_store,
        payload,
        config,
        evaluation_time=evaluation_time,
        raw_record=record,
    )


def resume_import_from_checkpoint(
    catalog: DatasetCatalog,
    raw_store: FileRawArtifactStore,
    config: HistoricalImportConfig,
    checkpoint_dir: Path,
    job_id: str,
    *,
    evaluation_time: datetime | None = None,
) -> HistoricalImportResult:
    """Resume a safely restartable import job from its last checkpoint."""
    checkpoint = load_import_checkpoint(checkpoint_dir, job_id)
    if checkpoint is None:
        msg = f"no checkpoint for job {job_id}"
        raise ValueError(msg)
    if checkpoint.phase == "published" and checkpoint.dataset_id:
        cached = _existing_published_result(
            catalog,
            checkpoint.dataset_id,
            checkpoint.raw_content_hash or "",
        )
        if cached is not None:
            return cached
    if checkpoint.raw_content_hash is None:
        msg = f"checkpoint {job_id} missing raw_content_hash"
        raise ValueError(msg)
    payload = raw_store.load(checkpoint.raw_content_hash)
    raw_record = None
    if checkpoint.raw_dataset_id:
        raw_record = RawArtifactRecord(
            raw_dataset_id=checkpoint.raw_dataset_id,
            content_hash=checkpoint.raw_content_hash,
            storage_relpath=f"raw/{checkpoint.raw_content_hash}.json",
            source=config.source,
            fetch_metadata={"resume": True, **config.import_configuration},
        )
    return import_from_raw_payload(
        catalog,
        raw_store,
        payload,
        config,
        evaluation_time=evaluation_time,
        checkpoint_dir=checkpoint_dir,
        job_id=job_id,
        raw_record=raw_record,
    )
