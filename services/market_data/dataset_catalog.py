"""Append-only dataset catalog (ADR-013)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from market_data.manifest import DatasetManifest, parse_manifest
from market_data.models import NormalizedCandle
from market_data.raw_store import RawArtifactRecord
from market_data.validation import candles_equal

if TYPE_CHECKING:
    from market_data.dataset_quality import DatasetQualityReportRecord
    from market_data.models import CandleConflict


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

    def persist_quality_report(
        self,
        dataset_id: str,
        record: DatasetQualityReportRecord,
        *,
        known_issues: tuple[str, ...] | None = None,
    ) -> None: ...

    def update_manifest_known_issues(
        self,
        dataset_id: str,
        known_issues: tuple[str, ...],
    ) -> None: ...

    def get_append_conflicts(self, dataset_id: str) -> tuple[CandleConflict, ...]: ...


@dataclass
class InMemoryDatasetCatalog:
    """Unit-test catalog without PostgreSQL."""

    _raw: dict[str, RawArtifactRecord] = field(default_factory=dict)
    _manifests: dict[str, DatasetManifest] = field(default_factory=dict)
    _candles: dict[str, tuple[NormalizedCandle, ...]] = field(default_factory=dict)
    _quality_reports: dict[str, DatasetQualityReportRecord] = field(default_factory=dict)
    _append_conflicts: dict[str, list] = field(default_factory=dict)

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
        existing_by_key = {(c.symbol, c.timeframe, c.open_time): c for c in existing}
        added = 0
        merged = list(existing)
        for candle in candles:
            key = (candle.symbol, candle.timeframe, candle.open_time)
            if key in keys:
                prior = existing_by_key[key]
                if not candles_equal(prior, candle):
                    from market_data.models import CandleConflict, CandleKey

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
            merged.append(candle)
            keys.add(key)
            existing_by_key[key] = candle
            added += 1
        self._candles[dataset_id] = tuple(sorted(merged, key=lambda c: c.open_time))
        return added

    def list_candles(self, dataset_id: str) -> tuple[NormalizedCandle, ...]:
        return self._candles.get(dataset_id, ())

    def persist_quality_report(
        self,
        dataset_id: str,
        record: DatasetQualityReportRecord,
        *,
        known_issues: tuple[str, ...] | None = None,
    ) -> None:
        if dataset_id not in self._manifests:
            raise DatasetCatalogError("unknown dataset")
        self._quality_reports[dataset_id] = record
        manifest = self._manifests[dataset_id]
        updates: dict = {
            "quality_status": record.report.status,
            "quality_report": record.report,
        }
        if known_issues:
            updates["known_issues"] = tuple(
                dict.fromkeys(manifest.known_issues + known_issues)
            )
        self._manifests[dataset_id] = manifest.model_copy(update=updates)

    def update_manifest_known_issues(
        self,
        dataset_id: str,
        known_issues: tuple[str, ...],
    ) -> None:
        if dataset_id not in self._manifests:
            raise DatasetCatalogError("unknown dataset")
        manifest = self._manifests[dataset_id]
        merged = tuple(dict.fromkeys(manifest.known_issues + known_issues))
        self._manifests[dataset_id] = manifest.model_copy(update={"known_issues": merged})

    def get_append_conflicts(self, dataset_id: str) -> tuple:
        stored = self._append_conflicts.get(dataset_id, [])
        return tuple(stored)


def manifest_from_row(manifest_json: dict[str, Any]) -> DatasetManifest:
    return parse_manifest(manifest_json)
