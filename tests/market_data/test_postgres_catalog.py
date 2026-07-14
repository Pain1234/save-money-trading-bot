"""PostgreSQL dataset catalog integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine

from market_data.content_hash import hash_normalized_candles
from market_data.dataset_quality import evaluate_dataset_quality
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.postgres_catalog import PostgresDatasetCatalog
from market_data.raw_store import RawArtifactRecord

from tests.market_data.conftest import dt, make_daily

EVAL = datetime(2026, 6, 1, tzinfo=UTC)


def _publish_btc_daily(
    catalog: PostgresDatasetCatalog,
    candles: tuple[NormalizedCandle, ...],
    *,
    raw_id: str,
) -> str:
    catalog.register_raw_artifact(
        RawArtifactRecord(raw_id, "b" * 64, "raw/b.json", "hl/mainnet", {})
    )
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=candles[0].open_time,
        end_timestamp=candles[-1].close_time,
        row_count=len(candles),
        content_hash=hash_normalized_candles(candles),
        raw_dataset_id=raw_id,
        raw_content_hash="b" * 64,
        code_commit="abc1234",
        created_at=EVAL,
    )
    published = catalog.publish_dataset(manifest)
    assert published.dataset_id is not None
    catalog.append_candles(published.dataset_id, candles)
    return published.dataset_id


@pytest.mark.postgres
def test_postgres_append_detects_conflicts(migrated_engine: Engine) -> None:
    catalog = PostgresDatasetCatalog(migrated_engine)
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
    dataset_id = _publish_btc_daily(catalog, (base,), raw_id="pg-conflict-raw")
    catalog.append_candles(dataset_id, (conflict,))
    record = evaluate_dataset_quality(
        catalog,
        dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        base.close_time,
    )
    assert record.conflict_count == 1
    assert len(catalog.get_append_conflicts(dataset_id)) == 1


@pytest.mark.postgres
def test_postgres_persist_quality_report_round_trips(migrated_engine: Engine) -> None:
    catalog = PostgresDatasetCatalog(migrated_engine)
    candle = make_daily(day=dt(2024, 2, 1))
    dataset_id = _publish_btc_daily(catalog, (candle,), raw_id="pg-quality-raw")
    record = evaluate_dataset_quality(
        catalog,
        dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        candle.close_time,
    )
    manifest = catalog.get_manifest(dataset_id)
    assert manifest.quality_report is not None
    assert manifest.quality_report.status == record.report.status
