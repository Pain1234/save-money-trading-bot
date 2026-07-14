"""End-to-end P3 reproducibility smoke test (#84)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from market_data.dataset_catalog import InMemoryDatasetCatalog
from market_data.historical_import import HistoricalImportConfig, import_from_raw_payload
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.quarantine import require_research_dataset
from market_data.raw_store import FileRawArtifactStore

FIXTURE = Path(__file__).parent / "fixtures" / "hyperliquid_daily_snapshot.json"
EVAL = datetime(2026, 1, 15, tzinfo=UTC)


def test_p3_pipeline_smoke(tmp_path) -> None:
    catalog = InMemoryDatasetCatalog()
    store = FileRawArtifactStore(tmp_path)
    config = HistoricalImportConfig(
        source="hyperliquid/mainnet",
        symbol=MarketSymbol.BTC,
        timeframe=MarketTimeframe.DAILY,
        code_commit="audit123",
        import_configuration={"audit": True},
    )
    result = import_from_raw_payload(
        catalog, store, FIXTURE.read_bytes(), config, evaluation_time=EVAL
    )
    manifest = require_research_dataset(
        catalog,
        result.manifest.dataset_id,
        MarketSymbol.BTC,
        MarketTimeframe.DAILY,
        EVAL,
    )
    assert manifest.dataset_id is not None
    assert len(catalog.list_candles(manifest.dataset_id)) == 2
