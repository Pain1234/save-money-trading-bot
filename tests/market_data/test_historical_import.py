"""Tests for historical import (#80)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from market_data.content_hash import hash_normalized_candles
from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.historical_import import (
    HistoricalImportConfig,
    _parse_hyperliquid_snapshot,
    import_from_raw_payload,
)
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.normalize import normalize_batch
from market_data.raw_store import FileRawArtifactStore

FIXTURE = Path(__file__).parent / "fixtures" / "hyperliquid_daily_snapshot.json"
EVAL_TIME = datetime(2026, 1, 15, tzinfo=UTC)


def test_import_from_fixture_is_deterministic(tmp_path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    payload = FIXTURE.read_bytes()
    config = HistoricalImportConfig(
        source="hyperliquid/mainnet",
        symbol=MarketSymbol.BTC,
        timeframe=MarketTimeframe.DAILY,
        code_commit="abc1234",
        import_configuration={"fixture": True},
    )
    first = import_from_raw_payload(catalog, store, payload, config, evaluation_time=EVAL_TIME)
    raws = _parse_hyperliquid_snapshot(payload, config, EVAL_TIME)
    normalized = normalize_batch(raws, EVAL_TIME)
    assert hash_normalized_candles(normalized) == first.manifest.content_hash
    assert first.candles_imported == 2
    reloaded = store.load(first.raw_content_hash)
    assert reloaded == payload
