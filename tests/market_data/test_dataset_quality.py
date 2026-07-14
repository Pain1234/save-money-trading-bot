"""Tests for dataset quality reports (#81)."""

from __future__ import annotations

from datetime import UTC, datetime

from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.dataset_quality import evaluate_dataset_quality
from market_data.models import DataQualityStatus, MarketSymbol, MarketTimeframe
from tests.market_data.conftest import make_daily_series

EVAL = datetime(2026, 6, 1, tzinfo=UTC)


def test_quality_valid_series() -> None:
    catalog = InMemoryDatasetCatalog()
    from market_data.raw_store import RawArtifactRecord

    catalog.register_raw_artifact(
        RawArtifactRecord("r1", "b" * 64, "raw/b.json", "hl/mainnet", {})
    )
    candles = make_daily_series(5, symbol=MarketSymbol.BTC)
    from market_data.content_hash import hash_normalized_candles
    from market_data.manifest import DatasetManifest

    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=candles[0].open_time,
        end_timestamp=candles[-1].close_time,
        row_count=len(candles),
        content_hash=hash_normalized_candles(candles),
        raw_dataset_id="r1",
        raw_content_hash="b" * 64,
        code_commit="abc1234",
        created_at=EVAL,
    )
    published = catalog.publish_dataset(manifest)
    catalog.append_candles(published.dataset_id, candles)
    record = evaluate_dataset_quality(
        catalog,
        published.dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        EVAL,
    )
    assert record.report.status in {DataQualityStatus.VALID, DataQualityStatus.STALE}
