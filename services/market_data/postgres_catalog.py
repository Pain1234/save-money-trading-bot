"""PostgreSQL append-only dataset catalog (ADR-013)."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from market_data.dataset_catalog import DatasetCatalogError
from market_data.manifest import DatasetManifest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.raw_store import RawArtifactRecord


class PostgresDatasetCatalog:
    """PostgreSQL-backed catalog; append-only by convention."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._append_conflicts: dict[str, list] = {}

    def register_raw_artifact(self, record: RawArtifactRecord) -> None:
        """Register one fetch observation; same bytes may have many raw_dataset_ids."""
        stmt = text(
            """
            INSERT INTO market_data_raw_artifacts
                (raw_dataset_id, content_hash, storage_relpath, source, fetch_metadata)
            VALUES
                (
                    :raw_dataset_id, :content_hash, :storage_relpath, :source,
                    CAST(:fetch_metadata AS jsonb)
                )
            ON CONFLICT (raw_dataset_id) DO NOTHING
            """
        )
        with self._engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "raw_dataset_id": record.raw_dataset_id,
                    "content_hash": record.content_hash,
                    "storage_relpath": record.storage_relpath,
                    "source": record.source,
                    "fetch_metadata": json.dumps(record.fetch_metadata),
                },
            )

    def publish_dataset(self, manifest: DatasetManifest) -> DatasetManifest:
        published = manifest.with_dataset_id()
        assert published.dataset_id is not None
        stmt = text(
            """
            INSERT INTO market_data_datasets
                (dataset_id, schema_version, manifest, raw_dataset_id, parent_dataset_id,
                 quality_status, layer)
            VALUES
                (:dataset_id, :schema_version, CAST(:manifest AS jsonb), :raw_dataset_id,
                 :parent_dataset_id, :quality_status, :layer)
            """
        )
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    stmt,
                    {
                        "dataset_id": published.dataset_id,
                        "schema_version": published.schema_version,
                        "manifest": json.dumps(published.to_catalog_dict()),
                        "raw_dataset_id": published.raw_dataset_id,
                        "parent_dataset_id": published.parent_dataset_id,
                        "quality_status": published.quality_status.value,
                        "layer": published.layer,
                    },
                )
        except Exception as exc:  # noqa: BLE001
            raise DatasetCatalogError(str(exc)) from exc
        return published

    def get_manifest(self, dataset_id: str) -> DatasetManifest:
        stmt = text(
            "SELECT manifest FROM market_data_datasets WHERE dataset_id = :dataset_id"
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt, {"dataset_id": dataset_id}).fetchone()
        if row is None:
            raise DatasetCatalogError(f"unknown dataset_id: {dataset_id}")
        from market_data.manifest import parse_manifest

        return parse_manifest(dict(row[0]))

    def append_candles(
        self,
        dataset_id: str,
        candles: tuple[NormalizedCandle, ...],
    ) -> int:
        from market_data.models import CandleConflict, CandleKey
        from market_data.validation import candles_equal

        existing = self.list_candles(dataset_id)
        keys = {(c.symbol, c.timeframe, c.open_time) for c in existing}
        existing_by_key = {(c.symbol, c.timeframe, c.open_time): c for c in existing}
        insert_stmt = text(
            """
            INSERT INTO market_data_normalized_candles
                (dataset_id, symbol, timeframe, open_time, close_time,
                 open, high, low, close, volume, is_closed)
            VALUES
                (:dataset_id, :symbol, :timeframe, :open_time, :close_time,
                 :open, :high, :low, :close, :volume, :is_closed)
            ON CONFLICT ON CONSTRAINT uq_market_data_normalized_candles_key DO NOTHING
            """
        )
        fetch_stmt = text(
            """
            SELECT symbol, timeframe, open_time, close_time,
                   open, high, low, close, volume, is_closed
            FROM market_data_normalized_candles
            WHERE dataset_id = :dataset_id
              AND symbol = :symbol
              AND timeframe = :timeframe
              AND open_time = :open_time
            """
        )
        added = 0
        with self._engine.begin() as conn:
            for candle in candles:
                key = (candle.symbol, candle.timeframe, candle.open_time)
                if key in keys:
                    prior = existing_by_key[key]
                    if not candles_equal(prior, candle):
                        conflict = CandleConflict(
                            key=CandleKey(
                                symbol=candle.symbol,
                                timeframe=candle.timeframe,
                                open_time=candle.open_time,
                            ),
                            existing=prior,
                            incoming=candle,
                        )
                        self._append_conflicts.setdefault(dataset_id, []).append(conflict)
                    continue
                result = conn.execute(
                    insert_stmt,
                    {
                        "dataset_id": dataset_id,
                        "symbol": candle.symbol.value,
                        "timeframe": candle.timeframe.value,
                        "open_time": candle.open_time,
                        "close_time": candle.close_time,
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                        "is_closed": candle.is_closed,
                    },
                )
                if result.rowcount:
                    added += 1
                    keys.add(key)
                    existing_by_key[key] = candle
                    continue
                row = conn.execute(
                    fetch_stmt,
                    {
                        "dataset_id": dataset_id,
                        "symbol": candle.symbol.value,
                        "timeframe": candle.timeframe.value,
                        "open_time": candle.open_time,
                    },
                ).fetchone()
                if row is None:
                    continue
                prior = NormalizedCandle(
                    symbol=MarketSymbol(row[0]),
                    timeframe=MarketTimeframe(row[1]),
                    open_time=row[2],
                    close_time=row[3],
                    open=Decimal(row[4]),
                    high=Decimal(row[5]),
                    low=Decimal(row[6]),
                    close=Decimal(row[7]),
                    volume=Decimal(row[8]),
                    is_closed=row[9],
                )
                if not candles_equal(prior, candle):
                    conflict = CandleConflict(
                        key=CandleKey(
                            symbol=candle.symbol,
                            timeframe=candle.timeframe,
                            open_time=candle.open_time,
                        ),
                        existing=prior,
                        incoming=candle,
                    )
                    self._append_conflicts.setdefault(dataset_id, []).append(conflict)
        return added

    def list_candles(self, dataset_id: str) -> tuple[NormalizedCandle, ...]:
        stmt = text(
            """
            SELECT symbol, timeframe, open_time, close_time,
                   open, high, low, close, volume, is_closed
            FROM market_data_normalized_candles
            WHERE dataset_id = :dataset_id
            ORDER BY open_time
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt, {"dataset_id": dataset_id}).fetchall()
        candles: list[NormalizedCandle] = []
        for row in rows:
            candles.append(
                NormalizedCandle(
                    symbol=MarketSymbol(row[0]),
                    timeframe=MarketTimeframe(row[1]),
                    open_time=row[2],
                    close_time=row[3],
                    open=Decimal(row[4]),
                    high=Decimal(row[5]),
                    low=Decimal(row[6]),
                    close=Decimal(row[7]),
                    volume=Decimal(row[8]),
                    is_closed=row[9],
                )
            )
        return tuple(candles)

    def persist_quality_report(
        self,
        dataset_id: str,
        record,
        *,
        known_issues: tuple[str, ...] | None = None,
    ) -> None:
        from market_data.dataset_quality import DatasetQualityReportRecord

        if not isinstance(record, DatasetQualityReportRecord):
            msg = "expected DatasetQualityReportRecord"
            raise TypeError(msg)
        manifest = self.get_manifest(dataset_id)
        merged_issues = manifest.known_issues
        if known_issues:
            merged_issues = tuple(dict.fromkeys(manifest.known_issues + known_issues))
        updated_manifest = manifest.model_copy(
            update={
                "quality_status": record.report.status,
                "known_issues": merged_issues,
                "quality_report": record.report,
            }
        )
        stmt = text(
            """
            UPDATE market_data_datasets
            SET quality_status = :quality_status,
                manifest = CAST(:manifest AS jsonb)
            WHERE dataset_id = :dataset_id
            """
        )
        with self._engine.begin() as conn:
            result = conn.execute(
                stmt,
                {
                    "dataset_id": dataset_id,
                    "quality_status": record.report.status.value,
                    "manifest": json.dumps(updated_manifest.to_catalog_dict()),
                },
            )
            if result.rowcount != 1:
                raise DatasetCatalogError(f"unknown dataset_id: {dataset_id}")

    def update_manifest_known_issues(
        self,
        dataset_id: str,
        known_issues: tuple[str, ...],
    ) -> None:
        manifest = self.get_manifest(dataset_id)
        merged = tuple(dict.fromkeys(manifest.known_issues + known_issues))
        updated_manifest = {
            **manifest.to_catalog_dict(),
            "known_issues": list(merged),
        }
        stmt = text(
            """
            UPDATE market_data_datasets
            SET manifest = CAST(:manifest AS jsonb)
            WHERE dataset_id = :dataset_id
            """
        )
        with self._engine.begin() as conn:
            result = conn.execute(
                stmt,
                {
                    "dataset_id": dataset_id,
                    "manifest": json.dumps(updated_manifest),
                },
            )
            if result.rowcount != 1:
                raise DatasetCatalogError(f"unknown dataset_id: {dataset_id}")

    def get_append_conflicts(self, dataset_id: str) -> tuple:
        stored = self._append_conflicts.get(dataset_id, [])
        return tuple(stored)
