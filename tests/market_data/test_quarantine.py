"""Tests for dataset quarantine (#82)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from market_data.content_hash import hash_normalized_candles
from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.manifest import DatasetManifest
from market_data.models import DataQualityStatus, MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.quarantine import QuarantineError, require_research_dataset
from market_data.raw_store import RawArtifactRecord


def _invalid_candle() -> NormalizedCandle:
    return NormalizedCandle(
        symbol=MarketSymbol.BTC,
        timeframe=MarketTimeframe.DAILY,
        open_time=datetime(2024, 1, 1, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        open=Decimal(10),
        high=Decimal(5),
        low=Decimal(9),
        close=Decimal(8),
        volume=Decimal(1),
        is_closed=True,
    )


def test_quarantine_blocks_invalid_dataset() -> None:
    catalog = InMemoryDatasetCatalog()
    catalog.register_raw_artifact(
        RawArtifactRecord("r1", "e" * 64, "raw/e.json", "hl/mainnet", {})
    )
    bad = (_invalid_candle(),)
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=bad[0].open_time,
        end_timestamp=bad[0].close_time,
        row_count=1,
        content_hash=hash_normalized_candles(bad),
        raw_dataset_id="r1",
        raw_content_hash="e" * 64,
        code_commit="abc1234",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        quality_status=DataQualityStatus.INVALID,
    )
    published = catalog.publish_dataset(manifest)
    catalog.append_candles(published.dataset_id, bad)
    with pytest.raises(QuarantineError):
        require_research_dataset(
            catalog,
            published.dataset_id,
            MarketSymbol.BTC,
            MarketTimeframe.DAILY,
            bad[0].close_time,
        )
