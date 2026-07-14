"""Append-only dataset catalog (ADR-013)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from market_data.manifest import DatasetManifest, parse_manifest
from market_data.models import NormalizedCandle
from market_data.raw_store import RawArtifactRecord


class DatasetCatalogError(Exception):
    """Fail-closed catalog error."""


class DatasetCatalog(Protocol):
    def register_raw_artifact(self, record: RawArtifactRecord) -> None: ...

    def publish_dataset(self, manifest: DatasetManifest) -> DatasetManifest: ...

    def get_manifest(self, dataset_id: str) -> DatasetManifest: ...

    def append_candles(
        self,
        dataset_id: str,
        candles: tuple[NormalizedCandle, ...],
    ) -> int: ...

    def list_candles(self, dataset_id: str) -> tuple[NormalizedCandle, ...]: ...


@dataclass
class InMemoryDatasetCatalog:
    """Unit-test catalog without PostgreSQL."""

    _raw: dict[str, RawArtifactRecord] = field(default_factory=dict)
    _manifests: dict[str, DatasetManifest] = field(default_factory=dict)
    _candles: dict[str, tuple[NormalizedCandle, ...]] = field(default_factory=dict)

    def register_raw_artifact(self, record: RawArtifactRecord) -> None:
        if record.raw_dataset_id in self._raw:
            existing = self._raw[record.raw_dataset_id]
            if existing.content_hash != record.content_hash:
                raise DatasetCatalogError("raw_dataset_id conflict")
            return
        self._raw[record.raw_dataset_id] = record

    def publish_dataset(self, manifest: DatasetManifest) -> DatasetManifest:
        published = manifest.with_dataset_id()
        assert published.dataset_id is not None
        if published.dataset_id in self._manifests:
            raise DatasetCatalogError("dataset already published")
        if published.raw_dataset_id not in self._raw:
            raise DatasetCatalogError("unknown raw_dataset_id")
        self._manifests[published.dataset_id] = published
        self._candles.setdefault(published.dataset_id, ())
        return published

    def get_manifest(self, dataset_id: str) -> DatasetManifest:
        if dataset_id not in self._manifests:
            raise DatasetCatalogError(f"unknown dataset_id: {dataset_id}")
        return self._manifests[dataset_id]

    def append_candles(
        self,
        dataset_id: str,
        candles: tuple[NormalizedCandle, ...],
    ) -> int:
        if dataset_id not in self._manifests:
            raise DatasetCatalogError("unknown dataset")
        existing = self._candles.get(dataset_id, ())
        keys = {(c.symbol, c.timeframe, c.open_time) for c in existing}
        added = 0
        merged = list(existing)
        for candle in candles:
            key = (candle.symbol, candle.timeframe, candle.open_time)
            if key in keys:
                continue
            merged.append(candle)
            keys.add(key)
            added += 1
        self._candles[dataset_id] = tuple(sorted(merged, key=lambda c: c.open_time))
        return added

    def list_candles(self, dataset_id: str) -> tuple[NormalizedCandle, ...]:
        return self._candles.get(dataset_id, ())


def manifest_from_row(manifest_json: dict[str, Any]) -> DatasetManifest:
    return parse_manifest(manifest_json)
