"""Bind research runs to P3 DatasetManifest + actual HistoricalDataBundle (#163)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backtester.models import FundingEvent, HistoricalDataBundle
from market_data.content_hash import (
    derive_dataset_id,
    hash_normalized_candles,
)
from market_data.manifest import DatasetManifest, parse_manifest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from strategy_engine.models import Candle

from research.experiment_spec import ExperimentSpec, TimeRange


def load_dataset_manifest(
    ref_path: str,
    *,
    repo_root: Path,
) -> DatasetManifest:
    """Load P3 DatasetManifest from Spec.manifest_path (repo-relative or absolute)."""
    path = Path(ref_path)
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        msg = f"DatasetManifest not found: {path}"
        raise FileNotFoundError(msg)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = "DatasetManifest root must be an object"
        raise ValueError(msg)
    return parse_manifest(raw)


def _candle_in_range(candle: Candle, time_range: TimeRange) -> bool:
    return time_range.start <= candle.open_time <= time_range.end


def _funding_in_range(event: FundingEvent, time_range: TimeRange) -> bool:
    return time_range.start <= event.timestamp <= time_range.end


def filter_bundle_to_time_range(
    bundle: HistoricalDataBundle,
    time_range: TimeRange,
    symbols: tuple[str, ...],
) -> HistoricalDataBundle:
    """Clip candles/funding to ExperimentSpec.time_range for configured symbols."""
    daily: dict[str, tuple[Any, ...]] = {}
    weekly: dict[str, tuple[Any, ...]] = {}
    monthly: dict[str, tuple[Any, ...]] = {}
    funding: dict[str, tuple[FundingEvent, ...]] = {}
    for sym in symbols:
        daily[sym] = tuple(
            c for c in bundle.daily.get(sym, ()) if _candle_in_range(c, time_range)
        )
        weekly[sym] = tuple(
            c for c in bundle.weekly.get(sym, ()) if _candle_in_range(c, time_range)
        )
        monthly[sym] = tuple(
            c for c in bundle.monthly.get(sym, ()) if _candle_in_range(c, time_range)
        )
        funding[sym] = tuple(
            e for e in bundle.funding.get(sym, ()) if _funding_in_range(e, time_range)
        )
    return HistoricalDataBundle(
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        funding=funding,
        data_quality_warnings=bundle.data_quality_warnings,
    )


def _to_normalized(candle: Candle) -> NormalizedCandle:
    return NormalizedCandle(
        symbol=MarketSymbol(candle.symbol),
        timeframe=MarketTimeframe(candle.timeframe.value),
        open_time=candle.open_time,
        close_time=candle.close_time,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        is_closed=candle.is_closed,
    )


def hash_research_bundle(
    bundle: HistoricalDataBundle,
    symbols: tuple[str, ...],
) -> str:
    """SHA-256 of sorted normalized candle rows in the (already filtered) bundle."""
    candles: list[NormalizedCandle] = []
    for sym in symbols:
        for series in (
            bundle.daily.get(sym, ()),
            bundle.weekly.get(sym, ()),
            bundle.monthly.get(sym, ()),
        ):
            for candle in series:
                candles.append(_to_normalized(candle))
    return hash_normalized_candles(tuple(candles))


def bind_dataset_to_bundle(
    spec: ExperimentSpec,
    bundle: HistoricalDataBundle,
    *,
    repo_root: Path,
) -> tuple[DatasetManifest, HistoricalDataBundle, str]:
    """Validate Spec ↔ Manifest ↔ Bundle; return filtered bundle + content hash.

    Fail-closed on any mismatch. Does not write artifacts.
    """
    ref = spec.dataset_manifest_ref
    if not ref.manifest_path:
        msg = "dataset_manifest_ref.manifest_path is required to bind input data"
        raise ValueError(msg)

    manifest = load_dataset_manifest(ref.manifest_path, repo_root=repo_root)

    if manifest.content_hash != ref.content_hash:
        msg = (
            "dataset content_hash mismatch: "
            f"spec={ref.content_hash} manifest={manifest.content_hash}"
        )
        raise ValueError(msg)

    expected_id = manifest.dataset_id or derive_dataset_id(
        manifest.content_hash, manifest.schema_version, manifest.source
    )
    if ref.dataset_id != expected_id:
        msg = (
            "dataset_id mismatch: "
            f"spec={ref.dataset_id!r} manifest={expected_id!r}"
        )
        raise ValueError(msg)

    manifest_symbols = {s.value for s in manifest.symbols}
    spec_symbols = {s.value for s in spec.symbols}
    if not spec_symbols.issubset(manifest_symbols):
        msg = (
            f"experiment symbols {sorted(spec_symbols)} not subset of "
            f"manifest symbols {sorted(manifest_symbols)}"
        )
        raise ValueError(msg)

    if spec.time_range.start < manifest.start_timestamp:
        msg = "time_range.start is before DatasetManifest.start_timestamp"
        raise ValueError(msg)
    if spec.time_range.end > manifest.end_timestamp:
        msg = "time_range.end is after DatasetManifest.end_timestamp"
        raise ValueError(msg)

    symbols = tuple(s.value for s in spec.symbols)
    filtered = filter_bundle_to_time_range(bundle, spec.time_range, symbols)
    if not any(filtered.daily.get(s) for s in symbols):
        msg = "no daily candles remain after applying time_range"
        raise ValueError(msg)

    # Candle open times must stay inside the declared research window.
    for sym in symbols:
        for c in filtered.daily.get(sym, ()):
            if c.open_time < spec.time_range.start or c.open_time > spec.time_range.end:
                msg = f"daily candle outside time_range for {sym}"
                raise ValueError(msg)

    actual_hash = hash_research_bundle(filtered, symbols)
    if actual_hash != ref.content_hash:
        msg = (
            "HistoricalDataBundle content does not match declared content_hash: "
            f"actual={actual_hash} declared={ref.content_hash}"
        )
        raise ValueError(msg)

    return manifest, filtered, actual_hash


def build_manifest_dict_for_bundle(
    *,
    bundle: HistoricalDataBundle,
    symbols: tuple[str, ...],
    time_range: TimeRange,
    source: str = "test/research",
    code_commit: str = "testhash",
) -> dict[str, Any]:
    """Helper for tests: build a DatasetManifest JSON matching a filtered bundle."""
    filtered = filter_bundle_to_time_range(bundle, time_range, symbols)
    content_hash = hash_research_bundle(filtered, symbols)
    row_count = sum(
        len(filtered.daily.get(s, ()))
        + len(filtered.weekly.get(s, ()))
        + len(filtered.monthly.get(s, ()))
        for s in symbols
    )
    schema_version = "1.0"
    dataset_id = derive_dataset_id(content_hash, schema_version, source)
    return {
        "schema_version": schema_version,
        "source": source,
        "symbols": list(symbols),
        "timeframes": ["1D", "1W", "1M"],
        "start_timestamp": time_range.start.isoformat().replace("+00:00", "+00:00"),
        "end_timestamp": time_range.end.isoformat().replace("+00:00", "+00:00"),
        "timezone": "UTC",
        "row_count": row_count,
        "content_hash": content_hash,
        "raw_dataset_id": f"raw-{dataset_id[:12]}",
        "raw_content_hash": content_hash,
        "import_configuration": {"purpose": "research-test"},
        "code_commit": code_commit,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "+00:00"),
        "parent_dataset_id": None,
        "quality_status": "VALID",
        "known_issues": [],
        "layer": "normalized",
        "dataset_id": dataset_id,
    }


# Public API
__all__ = [
    "bind_dataset_to_bundle",
    "build_manifest_dict_for_bundle",
    "filter_bundle_to_time_range",
    "hash_research_bundle",
    "load_dataset_manifest",
]
