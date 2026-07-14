"""Deterministic historical import from immutable raw artifacts (#80)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from market_data.content_hash import hash_normalized_candles
from market_data.dataset_catalog import DatasetCatalog
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.normalize import normalize_batch
from market_data.providers.hyperliquid import (
    HyperliquidCandleAdapter,
    coin_for_symbol,
    interval_for_timeframe,
)
from market_data.raw_store import FileRawArtifactStore


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


def import_from_raw_payload(
    catalog: DatasetCatalog,
    raw_store: FileRawArtifactStore,
    payload: bytes,
    config: HistoricalImportConfig,
    *,
    evaluation_time: datetime | None = None,
) -> HistoricalImportResult:
    """Capture raw bytes, normalize deterministically, publish dataset."""
    evaluation_time = evaluation_time or datetime.now(tz=UTC)
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
    )
    catalog.register_raw_artifact(record)

    raws = _parse_hyperliquid_snapshot(payload, config, evaluation_time)
    normalized = normalize_batch(raws, evaluation_time)
    if not normalized:
        msg = "no candles parsed from raw payload"
        raise ValueError(msg)

    content_hash = hash_normalized_candles(normalized)
    start = min(c.open_time for c in normalized)
    end = max(c.close_time for c in normalized)
    manifest = DatasetManifest(
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
    published = catalog.publish_dataset(manifest)
    assert published.dataset_id is not None
    added = catalog.append_candles(published.dataset_id, normalized)
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
    payload = raw_store.load(raw_content_hash)
    return import_from_raw_payload(
        catalog,
        raw_store,
        payload,
        config,
        evaluation_time=evaluation_time,
    )
