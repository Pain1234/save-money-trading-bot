"""Derived dataset aggregation with manifest parent link (#83)."""

from __future__ import annotations

from datetime import UTC, datetime

from market_data.aggregation import aggregate_weekly_from_daily
from market_data.content_hash import hash_aggregate_candles
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.timeframes import weekly_close, weekly_open_containing


def build_derived_weekly_manifest(
    parent: DatasetManifest,
    weekly_candles: tuple,
    *,
    code_commit: str,
) -> DatasetManifest:
    """Build derived manifest referencing parent daily dataset."""
    content_hash = hash_aggregate_candles(weekly_candles)
    return DatasetManifest(
        source=parent.source,
        symbols=parent.symbols,
        timeframes=(MarketTimeframe.WEEKLY,),
        start_timestamp=weekly_candles[0].open_time,
        end_timestamp=weekly_candles[-1].close_time,
        row_count=len(weekly_candles),
        content_hash=content_hash,
        raw_dataset_id=parent.raw_dataset_id,
        raw_content_hash=parent.raw_content_hash,
        import_configuration=parent.import_configuration,
        code_commit=code_commit,
        created_at=datetime.now(tz=UTC),
        parent_dataset_id=parent.dataset_id,
        layer="derived",
    )


def derive_iso_weekly_from_parent(
    parent: DatasetManifest,
    dailies: tuple,
    symbol: MarketSymbol,
    evaluation_time: datetime,
    *,
    code_commit: str,
) -> tuple[DatasetManifest, tuple]:
    """Aggregate ISO weekly candles and return derived manifest."""
    assert parent.dataset_id is not None
    monday = weekly_open_containing(dailies[0].open_time)
    close = weekly_close(monday)
    weekly = aggregate_weekly_from_daily(dailies, symbol, close)
    manifest = build_derived_weekly_manifest(
        parent,
        weekly,
        code_commit=code_commit,
    )
    return manifest, weekly
