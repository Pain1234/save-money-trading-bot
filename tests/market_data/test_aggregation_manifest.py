"""Aggregation manifest and ADR-006 regression (#83)."""

from __future__ import annotations

from datetime import UTC, datetime

from market_data.content_hash import hash_normalized_candles
from market_data.derived_dataset import derive_iso_weekly_from_parent
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe
from tests.market_data.conftest import dt, make_daily_series


def test_derived_manifest_links_parent() -> None:
    dailies = make_daily_series(14, start=dt(2024, 1, 1), symbol=MarketSymbol.BTC)
    parent_hash = hash_normalized_candles(dailies)
    parent = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=dailies[0].open_time,
        end_timestamp=dailies[-1].close_time,
        row_count=len(dailies),
        content_hash=parent_hash,
        raw_dataset_id="raw-parent",
        raw_content_hash="c" * 64,
        code_commit="abc1234",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ).with_dataset_id()
    eval_time = dailies[-1].close_time
    derived_manifest, weekly = derive_iso_weekly_from_parent(
        parent,
        dailies,
        MarketSymbol.BTC,
        eval_time,
        code_commit="abc1234",
    )
    assert derived_manifest.parent_dataset_id == parent.dataset_id
    assert derived_manifest.layer == "derived"
    assert len(weekly) >= 1


def test_aggregation_deterministic() -> None:
    dailies = make_daily_series(7, start=dt(2024, 1, 1))
    parent = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=dailies[0].open_time,
        end_timestamp=dailies[-1].close_time,
        row_count=len(dailies),
        content_hash=hash_normalized_candles(dailies),
        raw_dataset_id="raw",
        raw_content_hash="d" * 64,
        code_commit="abc1234",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ).with_dataset_id()
    eval_time = dailies[-1].close_time
    m1, w1 = derive_iso_weekly_from_parent(
        parent, dailies, MarketSymbol.BTC, eval_time, code_commit="abc1234"
    )
    m2, w2 = derive_iso_weekly_from_parent(
        parent, dailies, MarketSymbol.BTC, eval_time, code_commit="abc1234"
    )
    assert m1.content_hash == m2.content_hash
    assert len(w1) == len(w2)
