"""Tests for dataset catalog and raw store (#79)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_data.content_hash import hash_normalized_candles
from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.manifest import DatasetManifest
from market_data.models import DataQualityStatus, MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.raw_store import FileRawArtifactStore, RawArtifactRecord


def test_raw_store_immutable(tmp_path) -> None:
    store = FileRawArtifactStore(tmp_path)
    payload = b'{"page":1}'
    rec = store.store(payload, source="hyperliquid/mainnet", fetch_metadata={"page": 1})
    assert store.load(rec.content_hash) == payload
    rec2 = store.store(payload, source="hyperliquid/mainnet", fetch_metadata={"page": 1})
    assert rec2.content_hash == rec.content_hash
    other = store.store(b'{"page":2}', source="hyperliquid/mainnet", fetch_metadata={"page": 2})
    assert other.content_hash != rec.content_hash


def test_catalog_publish_and_candles() -> None:
    catalog = InMemoryDatasetCatalog()

    record = RawArtifactRecord(
        raw_dataset_id="raw001",
        content_hash="a" * 64,
        storage_relpath="raw/a.json",
        source="hyperliquid/mainnet",
        fetch_metadata={},
    )
    catalog.register_raw_artifact(record)
    candle = NormalizedCandle(
        symbol=MarketSymbol.BTC,
        timeframe=MarketTimeframe.DAILY,
        open_time=datetime(2024, 1, 1, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        open=Decimal(1),
        high=Decimal(2),
        low=Decimal(1),
        close=Decimal(2),
        volume=Decimal(10),
        is_closed=True,
    )
    content_hash = hash_normalized_candles((candle,))
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        end_timestamp=datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        row_count=1,
        content_hash=content_hash,
        raw_dataset_id="raw001",
        raw_content_hash="a" * 64,
        code_commit="deadbeef",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        quality_status=DataQualityStatus.VALID,
    )
    published = catalog.publish_dataset(manifest)
    assert published.dataset_id is not None
    assert catalog.append_candles(published.dataset_id, (candle,)) == 1
    assert catalog.append_candles(published.dataset_id, (candle,)) == 0
    assert len(catalog.list_candles(published.dataset_id)) == 1
