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

from tests.market_data.conftest import make_daily_series


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


def test_quarantine_blocks_stale_without_waiver() -> None:
    catalog = InMemoryDatasetCatalog()
    catalog.register_raw_artifact(
        RawArtifactRecord("r2", "f" * 64, "raw/f.json", "hl/mainnet", {})
    )
    candles = make_daily_series(3, symbol=MarketSymbol.BTC)
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=candles[0].open_time,
        end_timestamp=candles[-1].close_time,
        row_count=len(candles),
        content_hash=hash_normalized_candles(candles),
        raw_dataset_id="r2",
        raw_content_hash="f" * 64,
        code_commit="abc1234",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    published = catalog.publish_dataset(manifest)
    catalog.append_candles(published.dataset_id, candles)
    stale_eval = datetime(2099, 1, 1, tzinfo=UTC)
    with pytest.raises(QuarantineError):
        require_research_dataset(
            catalog,
            published.dataset_id,
            MarketSymbol.BTC,
            MarketTimeframe.DAILY,
            stale_eval,
        )


def test_quarantine_allows_stale_with_explicit_waiver() -> None:
    catalog = InMemoryDatasetCatalog()
    catalog.register_raw_artifact(
        RawArtifactRecord("r3", "a" * 64, "raw/a.json", "hl/mainnet", {})
    )
    candles = make_daily_series(3, symbol=MarketSymbol.BTC)
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=candles[0].open_time,
        end_timestamp=candles[-1].close_time,
        row_count=len(candles),
        content_hash=hash_normalized_candles(candles),
        raw_dataset_id="r3",
        raw_content_hash="a" * 64,
        code_commit="abc1234",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        allow_quality_warnings=True,
    )
    published = catalog.publish_dataset(manifest)
    catalog.append_candles(published.dataset_id, candles)
    stale_eval = datetime(2099, 1, 1, tzinfo=UTC)
    result = require_research_dataset(
        catalog,
        published.dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        stale_eval,
    )
    assert result.allow_quality_warnings is True
    assert result.known_issues


def test_quarantine_blocks_empty_dataset() -> None:
    catalog = InMemoryDatasetCatalog()
    catalog.register_raw_artifact(
        RawArtifactRecord("r4", "b" * 64, "raw/b.json", "hl/mainnet", {})
    )
    eval_time = datetime(2026, 1, 1, tzinfo=UTC)
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=eval_time,
        end_timestamp=eval_time,
        row_count=0,
        content_hash="c" * 64,
        raw_dataset_id="r4",
        raw_content_hash="b" * 64,
        code_commit="abc1234",
        created_at=eval_time,
    )
    published = catalog.publish_dataset(manifest)
    with pytest.raises(QuarantineError):
        require_research_dataset(
            catalog,
            published.dataset_id,
            MarketSymbol.BTC,
            MarketTimeframe.DAILY,
            eval_time,
        )
