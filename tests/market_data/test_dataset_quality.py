"""Tests for dataset quality reports (#81)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_data.content_hash import hash_normalized_candles
from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.dataset_quality import evaluate_dataset_quality
from market_data.manifest import DatasetManifest
from market_data.models import DataQualityStatus, MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.raw_store import RawArtifactRecord

from tests.market_data.conftest import dt, make_daily, make_daily_series

EVAL = datetime(2026, 6, 1, tzinfo=UTC)


def _publish_series(
    catalog: InMemoryDatasetCatalog,
    candles: tuple[NormalizedCandle, ...],
) -> str:
    catalog.register_raw_artifact(
        RawArtifactRecord("r1", "b" * 64, "raw/b.json", "hl/mainnet", {})
    )
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
    return published.dataset_id


def test_quality_valid_series() -> None:
    catalog = InMemoryDatasetCatalog()
    candles = make_daily_series(5, symbol=MarketSymbol.BTC)
    dataset_id = _publish_series(catalog, candles)
    eval_time = candles[-1].close_time
    record = evaluate_dataset_quality(
        catalog,
        dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        eval_time,
    )
    assert record.gap_count == 0
    assert record.conflict_count == 0
    assert record.report.status == DataQualityStatus.VALID
    manifest = catalog.get_manifest(dataset_id)
    assert manifest.quality_status == DataQualityStatus.VALID
    assert manifest.quality_report is not None
    assert manifest.quality_report.status == DataQualityStatus.VALID


def test_quality_detects_gap() -> None:
    catalog = InMemoryDatasetCatalog()
    day1 = make_daily(day=dt(2024, 1, 1))
    day3 = make_daily(day=dt(2024, 1, 3))
    candles = (day1, day3)
    dataset_id = _publish_series(catalog, candles)
    record = evaluate_dataset_quality(
        catalog,
        dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        day3.close_time,
    )
    assert record.gap_count >= 1
    assert record.report.status == DataQualityStatus.INCOMPLETE
    assert catalog.get_manifest(dataset_id).quality_status == DataQualityStatus.INCOMPLETE


def test_quality_detects_duplicate_conflict() -> None:
    catalog = InMemoryDatasetCatalog()
    base = make_daily(day=dt(2024, 1, 1))
    conflict = NormalizedCandle(
        symbol=base.symbol,
        timeframe=base.timeframe,
        open_time=base.open_time,
        close_time=base.close_time,
        open=Decimal("200"),
        high=Decimal("201"),
        low=Decimal("199"),
        close=Decimal("200"),
        volume=Decimal("1"),
        is_closed=True,
    )
    dataset_id = _publish_series(catalog, (base,))
    catalog.append_candles(dataset_id, (conflict,))
    record = evaluate_dataset_quality(
        catalog,
        dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        base.close_time,
    )
    assert record.conflict_count == 1
    assert record.report.status == DataQualityStatus.INVALID


def test_quality_empty_series_is_incomplete_not_stale() -> None:
    catalog = InMemoryDatasetCatalog()
    catalog.register_raw_artifact(
        RawArtifactRecord("r-empty", "c" * 64, "raw/c.json", "hl/mainnet", {})
    )
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=EVAL,
        end_timestamp=EVAL,
        row_count=0,
        content_hash="d" * 64,
        raw_dataset_id="r-empty",
        raw_content_hash="c" * 64,
        code_commit="abc1234",
        created_at=EVAL,
    )
    published = catalog.publish_dataset(manifest)
    record = evaluate_dataset_quality(
        catalog,
        published.dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        EVAL,
    )
    assert record.report.status == DataQualityStatus.INCOMPLETE
    assert record.stale is False
