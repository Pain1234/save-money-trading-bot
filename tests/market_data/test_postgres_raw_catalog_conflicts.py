"""PostgreSQL raw artifact identity conflict tests."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from market_data.dataset_catalog import DatasetCatalogError
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe
from market_data.postgres_catalog import PostgresDatasetCatalog
from market_data.raw_store import RawArtifactRecord
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


@pytest.fixture(autouse=True)
def _reset_postgres_trading_tables_before_test() -> Iterator[None]:
    """Override the shared destructive reset; these tests clean up unique rows."""
    yield


@pytest.fixture(scope="module")
def catalog_engine(alembic_config: Config) -> Iterator[Engine]:
    """Upgrade in place without downgrading or resetting a shared test database."""
    command.upgrade(alembic_config, "head")
    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url"), pool_pre_ping=True)
    yield engine
    engine.dispose()


def _record(raw_dataset_id: str, content_hash: str) -> RawArtifactRecord:
    return RawArtifactRecord(
        raw_dataset_id=raw_dataset_id,
        content_hash=content_hash,
        storage_relpath=f"raw/{content_hash}.json",
        source="hyperliquid/mainnet",
        fetch_metadata={},
    )


def _delete_raw_artifact(engine: Engine, raw_dataset_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM market_data_datasets "
                "WHERE raw_dataset_id = :raw_dataset_id"
            ),
            {"raw_dataset_id": raw_dataset_id},
        )
        conn.execute(
            text(
                "DELETE FROM market_data_raw_artifacts "
                "WHERE raw_dataset_id = :raw_dataset_id"
            ),
            {"raw_dataset_id": raw_dataset_id},
        )


@pytest.mark.postgres
def test_register_raw_artifact_rejects_sequential_hash_conflict(
    catalog_engine: Engine,
) -> None:
    raw_dataset_id = f"test-374-sequential-{uuid4().hex}"
    catalog = PostgresDatasetCatalog(catalog_engine)
    try:
        catalog.register_raw_artifact(_record(raw_dataset_id, "a" * 64))
        catalog.register_raw_artifact(_record(raw_dataset_id, "a" * 64))

        with pytest.raises(DatasetCatalogError, match="raw_dataset_id conflict"):
            catalog.register_raw_artifact(_record(raw_dataset_id, "b" * 64))

        with catalog_engine.connect() as conn:
            stored_hash = conn.execute(
                text(
                    "SELECT content_hash FROM market_data_raw_artifacts "
                    "WHERE raw_dataset_id = :raw_dataset_id"
                ),
                {"raw_dataset_id": raw_dataset_id},
            ).scalar_one()
        assert stored_hash == "a" * 64
    finally:
        _delete_raw_artifact(catalog_engine, raw_dataset_id)


@pytest.mark.postgres
def test_register_raw_artifact_rejects_concurrent_hash_conflict(
    catalog_engine: Engine,
) -> None:
    raw_dataset_id = f"test-374-concurrent-{uuid4().hex}"
    barrier = Barrier(2)

    def register(content_hash: str) -> str:
        barrier.wait()
        try:
            PostgresDatasetCatalog(catalog_engine).register_raw_artifact(
                _record(raw_dataset_id, content_hash)
            )
        except DatasetCatalogError:
            return "conflict"
        return "registered"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(register, ("c" * 64, "d" * 64)))
        assert sorted(outcomes) == ["conflict", "registered"]
    finally:
        _delete_raw_artifact(catalog_engine, raw_dataset_id)


@pytest.mark.postgres
def test_publish_dataset_rejects_mismatched_raw_content_hash(
    catalog_engine: Engine,
) -> None:
    raw_dataset_id = f"test-374-manifest-{uuid4().hex}"
    normalized_content_hash = uuid4().hex * 2
    catalog = PostgresDatasetCatalog(catalog_engine)
    catalog.register_raw_artifact(_record(raw_dataset_id, "e" * 64))
    manifest = DatasetManifest(
        source="hyperliquid/mainnet",
        symbols=(MarketSymbol.BTC,),
        timeframes=(MarketTimeframe.DAILY,),
        start_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        end_timestamp=datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        row_count=1,
        content_hash=normalized_content_hash,
        raw_dataset_id=raw_dataset_id,
        raw_content_hash="0" * 64,
        code_commit="abc1234",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    published = manifest.with_dataset_id()
    assert published.dataset_id is not None
    try:
        with pytest.raises(DatasetCatalogError, match="raw artifact hash mismatch"):
            catalog.publish_dataset(manifest)

        with catalog_engine.connect() as conn:
            dataset_count = conn.execute(
                text(
                    "SELECT count(*) FROM market_data_datasets "
                    "WHERE dataset_id = :dataset_id"
                ),
                {"dataset_id": published.dataset_id},
            ).scalar_one()
        assert dataset_count == 0
    finally:
        _delete_raw_artifact(catalog_engine, raw_dataset_id)
