"""Export Hyperliquid public candles into versioned Lab catalog snapshots (#274).

Does not import into Postgres. Builds real raw-page provenance (not the test
helper ``build_manifest_dict_for_bundle``).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtester.models import HistoricalDataBundle
from market_data.aggregation import aggregate_monthly_from_daily, aggregate_weekly_from_daily
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.content_hash import derive_dataset_id, hash_raw_bytes
from market_data.dataset_quality import evaluate_series_quality
from market_data.manifest import DatasetManifest, parse_manifest
from market_data.models import (
    DataQualityStatus,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    RawCandle,
)
from market_data.network.http_client import HyperliquidHttpClient
from market_data.normalize import normalize_batch
from market_data.providers.hyperliquid_historical import HyperliquidHistoricalProvider
from market_data.timeframes import daily_close, daily_open, ensure_utc
from market_data.validation import sort_candles

from research.dataset_binding import hash_research_bundle

DEFAULT_DAYS = 730
SCHEMA_VERSION = "1.0"
PROVIDER_VERSION = "hyperliquid_historical/1.0"

# Optional mid-write hook for fail-injection tests (staging Path).
SnapshotWriteHook = Callable[[Path], None]


class HlDatasetExportError(ValueError):
    """Fail-closed export / catalog update error."""


@dataclass(frozen=True)
class ExportWindow:
    """Inclusive closed UTC daily window (start day open → end day close)."""

    start_open: datetime
    end_close: datetime
    days: int
    as_of: datetime
    end_date: date

    @property
    def start_timestamp(self) -> datetime:
        return self.start_open

    @property
    def end_timestamp(self) -> datetime:
        return self.end_close


@dataclass(frozen=True)
class ExportResult:
    dataset_id: str
    content_hash: str
    raw_content_hash: str
    snapshot_dir: Path
    catalog_path: Path
    catalog_alias: str
    daily_count: int
    weekly_count: int
    monthly_count: int
    wrote_snapshot: bool
    catalog_updated: bool
    code_commit: str


def dumps_deterministic(obj: Any) -> str:
    """Stable JSON for byte-identical re-exports."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def default_catalog_alias(
    symbol: MarketSymbol,
    network: HyperliquidNetwork,
    days: int,
) -> str:
    """Catalog selector id derived from symbol / network / day count."""
    return f"hl-{symbol.value.lower()}-{network.value}-{days}d"


def raw_source_for_network(network: HyperliquidNetwork) -> str:
    return f"hyperliquid/{network.value}/raw"


def parse_as_of(value: str) -> datetime:
    """Parse ``--as-of`` / ``--end-date`` pin (date or ISO datetime)."""
    text = value.strip()
    if not text:
        raise HlDatasetExportError("as-of / end-date must be non-empty")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        d = date.fromisoformat(text)
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=UTC)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return ensure_utc(parsed)


def last_closed_utc_day(as_of: datetime) -> date:
    """Last fully closed UTC calendar day at ``as_of`` (open daily candle excluded)."""
    as_of = ensure_utc(as_of)
    today_open = daily_open(as_of)
    today_close = daily_close(today_open)
    if as_of >= today_close:
        return today_open.date()
    return (today_open - timedelta(days=1)).date()


def resolve_export_window(*, as_of: datetime, days: int) -> ExportWindow:
    if days < 1:
        raise HlDatasetExportError("days must be >= 1")
    end_date = last_closed_utc_day(as_of)
    end_open = datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC)
    end_close = daily_close(end_open)
    start_open = end_open - timedelta(days=days - 1)
    return ExportWindow(
        start_open=start_open,
        end_close=end_close,
        days=days,
        as_of=ensure_utc(as_of),
        end_date=end_date,
    )


def resolve_export_code_commit(
    *,
    explicit: str | None,
    repo_root: Path,
) -> str:
    """Real code provenance: ``--code-commit``, env pin, or clean Git HEAD."""
    if explicit is not None:
        pinned = explicit.strip()
        if len(pinned) < 7 or pinned.lower() == "unknown":
            raise HlDatasetExportError(
                "code_commit must be a real git SHA (min 7 chars), not unknown"
            )
        return pinned
    try:
        from research.runner import resolve_git_commit

        return resolve_git_commit(repo_root, allow_dirty=False)
    except ValueError as exc:
        raise HlDatasetExportError(str(exc)) from exc


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _dir_bytes_fingerprint(root: Path) -> dict[str, str]:
    """Relative path → sha256 of file bytes (sorted keys for compare)."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            out[rel] = hash_raw_bytes(path.read_bytes())
    return out


def write_raw_pages(
    snapshot_dir: Path,
    pages: tuple[bytes, ...],
    *,
    network: HyperliquidNetwork,
) -> tuple[str, str]:
    """Content-addressed raw pages; returns (raw_content_hash, raw_dataset_id)."""
    raw_root = snapshot_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    page_hashes: list[str] = []
    for index, page in enumerate(pages):
        page_hash = hash_raw_bytes(page)
        page_hashes.append(page_hash)
        target = raw_root / page_hash
        if not target.exists():
            target.write_bytes(page)
        index_path = raw_root / f"page_{index:04d}.sha256"
        index_path.write_text(page_hash + "\n", encoding="utf-8", newline="\n")

    raw_content_hash = hash_raw_bytes(b"".join(pages))
    raw_dataset_id = derive_dataset_id(
        raw_content_hash, SCHEMA_VERSION, raw_source_for_network(network)
    )
    index_doc = {
        "algorithm": "sha256",
        "page_count": len(pages),
        "pages": page_hashes,
        "raw_content_hash": raw_content_hash,
        "raw_dataset_id": raw_dataset_id,
        "source": raw_source_for_network(network),
    }
    (raw_root / "index.json").write_text(dumps_deterministic(index_doc), encoding="utf-8")
    return raw_content_hash, raw_dataset_id


def _materialize_snapshot(
    target: Path,
    *,
    pages: tuple[bytes, ...],
    bundle: HistoricalDataBundle,
    manifest: DatasetManifest,
    network: HyperliquidNetwork,
    write_hook: SnapshotWriteHook | None = None,
) -> None:
    """Write full snapshot layout under ``target`` (callers own atomicity)."""
    write_raw_pages(target, pages, network=network)
    if write_hook is not None:
        write_hook(target)
    (target / "bundle.json").write_text(_bundle_json_bytes(bundle), encoding="utf-8", newline="\n")
    (target / "dataset_manifest.json").write_text(
        _manifest_json_bytes(manifest), encoding="utf-8", newline="\n"
    )


def raw_candles_from_hl_pages(
    pages: tuple[bytes, ...],
    *,
    symbol: MarketSymbol,
    evaluation_time: datetime,
) -> tuple[RawCandle, ...]:
    """Parse stored candleSnapshot page bytes (offline / replay)."""
    from market_data.network.json_utils import loads_decimal
    from market_data.providers.hyperliquid import (
        HyperliquidCandleAdapter,
        coin_for_symbol,
        interval_for_timeframe,
    )

    adapter = HyperliquidCandleAdapter()
    coin = coin_for_symbol(symbol)
    interval = interval_for_timeframe(MarketTimeframe.DAILY)
    evaluation_time = ensure_utc(evaluation_time)
    candles: list[RawCandle] = []
    seen: set[tuple[datetime, datetime]] = set()
    for page in pages:
        payload = loads_decimal(page.decode("utf-8"))
        if not isinstance(payload, list):
            raise HlDatasetExportError("raw page must be a JSON list")
        for item in payload:
            if not isinstance(item, dict):
                raise HlDatasetExportError("raw page item must be an object")
            raw = adapter.parse_candle(
                item,
                expected_coin=coin,
                expected_interval=interval,
                evaluation_time=evaluation_time,
                strict=True,
            )
            key = (raw.open_time, raw.close_time)
            if key in seen:
                continue
            seen.add(key)
            candles.append(raw)
    candles.sort(key=lambda c: c.open_time)
    return tuple(candles)


def build_research_bundle(
    daily_normalized: tuple[NormalizedCandle, ...],
    *,
    symbol: MarketSymbol,
    evaluation_time: datetime,
) -> HistoricalDataBundle:
    evaluation_time = ensure_utc(evaluation_time)
    daily = sort_candles(daily_normalized)
    weekly = aggregate_weekly_from_daily(daily, symbol, evaluation_time)
    monthly = aggregate_monthly_from_daily(daily, symbol, evaluation_time)
    sym = symbol.value
    return HistoricalDataBundle(
        daily={sym: tuple(c.to_strategy_candle() for c in daily)},
        weekly={sym: tuple(c.to_strategy_candle() for c in weekly)},
        monthly={sym: tuple(c.to_strategy_candle() for c in monthly)},
        funding={},
    )


def assert_daily_window(
    daily: tuple[NormalizedCandle, ...],
    window: ExportWindow,
    *,
    symbol: MarketSymbol,
) -> None:
    """Require exact ``days`` gapless closed dailies covering the declared window."""
    expected_opens = [window.start_open + timedelta(days=i) for i in range(window.days)]
    if len(daily) != window.days:
        raise HlDatasetExportError(
            f"expected exactly {window.days} daily candles, got {len(daily)}"
        )
    for candle, expected_open in zip(daily, expected_opens, strict=True):
        if candle.symbol != symbol:
            raise HlDatasetExportError(f"unexpected symbol {candle.symbol}")
        if candle.timeframe != MarketTimeframe.DAILY:
            raise HlDatasetExportError("daily series contains non-daily candle")
        if candle.open_time != expected_open:
            raise HlDatasetExportError(
                f"daily open_time mismatch: got {candle.open_time.isoformat()} "
                f"expected {expected_open.isoformat()}"
            )
        if not candle.is_closed:
            raise HlDatasetExportError(f"open daily candle at {candle.open_time.isoformat()}")
        if candle.close_time != daily_close(expected_open):
            raise HlDatasetExportError(
                f"daily close_time mismatch at {candle.open_time.isoformat()}"
            )


def require_quality_valid(
    bundle: HistoricalDataBundle,
    *,
    symbol: MarketSymbol,
    evaluation_time: datetime,
) -> dict[str, Any]:
    """Run D/W/M quality; abort unless all VALID."""
    from research.dataset_binding import _to_normalized

    sym = symbol.value
    daily_n = tuple(_to_normalized(c) for c in bundle.daily.get(sym, ()))
    weekly_n = tuple(_to_normalized(c) for c in bundle.weekly.get(sym, ()))
    monthly_n = tuple(_to_normalized(c) for c in bundle.monthly.get(sym, ()))
    reports = {
        "1D": evaluate_series_quality(daily_n, symbol, MarketTimeframe.DAILY, evaluation_time),
        "1W": evaluate_series_quality(weekly_n, symbol, MarketTimeframe.WEEKLY, evaluation_time),
        "1M": evaluate_series_quality(monthly_n, symbol, MarketTimeframe.MONTHLY, evaluation_time),
    }
    for tf, report in reports.items():
        if report.status is not DataQualityStatus.VALID:
            raise HlDatasetExportError(
                f"quality gate failed for {tf}: status={report.status.value} "
                f"reasons={[r.value for r in report.reason_codes]} "
                f"messages={list(report.messages)}"
            )
    return {
        tf: {
            "status": r.status.value,
            "reason_codes": [c.value for c in r.reason_codes],
            "gap_count": len(r.gaps),
            "conflict_count": len(r.conflicts),
        }
        for tf, r in reports.items()
    }


def build_export_manifest(
    *,
    bundle: HistoricalDataBundle,
    symbols: tuple[str, ...],
    window: ExportWindow,
    source: str,
    raw_content_hash: str,
    raw_dataset_id: str,
    import_configuration: dict[str, Any],
    quality_summary: dict[str, Any],
    code_commit: str,
) -> DatasetManifest:
    """Canonical export manifest (not ``build_manifest_dict_for_bundle``)."""
    if len(code_commit) < 7 or code_commit.lower() == "unknown":
        raise HlDatasetExportError("code_commit must be a real git SHA (min 7 chars)")
    content_hash = hash_research_bundle(bundle, symbols)
    row_count = sum(
        len(bundle.daily.get(s, ()))
        + len(bundle.weekly.get(s, ()))
        + len(bundle.monthly.get(s, ()))
        for s in symbols
    )
    # created_at pinned to as-of so same inputs (+ code_commit) → same bytes.
    created_at = window.as_of
    data = {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "symbols": list(symbols),
        "timeframes": ["1D", "1W", "1M"],
        "start_timestamp": window.start_timestamp.isoformat().replace("+00:00", "+00:00"),
        "end_timestamp": window.end_timestamp.isoformat().replace("+00:00", "+00:00"),
        "timezone": "UTC",
        "row_count": row_count,
        "content_hash": content_hash,
        "raw_dataset_id": raw_dataset_id,
        "raw_content_hash": raw_content_hash,
        "import_configuration": {
            **import_configuration,
            "quality_summary": quality_summary,
        },
        "code_commit": code_commit,
        "created_at": created_at.isoformat().replace("+00:00", "+00:00"),
        "parent_dataset_id": None,
        "quality_status": DataQualityStatus.VALID.value,
        "allow_quality_warnings": False,
        "known_issues": [],
        "layer": "normalized",
    }
    return parse_manifest(data)


def _bundle_json_bytes(bundle: HistoricalDataBundle) -> str:
    return dumps_deterministic(bundle.model_dump(mode="json"))


def _manifest_json_bytes(manifest: DatasetManifest) -> str:
    return dumps_deterministic(manifest.to_catalog_dict())


def write_snapshot_if_absent(
    snapshot_dir: Path,
    *,
    pages: tuple[bytes, ...],
    bundle: HistoricalDataBundle,
    manifest: DatasetManifest,
    network: HyperliquidNetwork,
    write_hook: SnapshotWriteHook | None = None,
) -> bool:
    """Atomically publish snapshot; identical re-run OK; divergent exists fails closed.

    Materializes under a sibling staging directory, then ``os.replace`` into
    ``snapshot_dir`` only after the full layout is written. Mid-write failures
    leave no final directory.
    """
    snapshot_dir = snapshot_dir.resolve()
    parent = snapshot_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{snapshot_dir.name}.write.{os.getpid()}"

    def _cleanup_staging() -> None:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    try:
        if snapshot_dir.exists():
            _cleanup_staging()
            staging.mkdir(parents=True)
            _materialize_snapshot(
                staging,
                pages=pages,
                bundle=bundle,
                manifest=manifest,
                network=network,
            )
            expected = _dir_bytes_fingerprint(staging)
            actual = _dir_bytes_fingerprint(snapshot_dir)
            if actual != expected:
                raise HlDatasetExportError(
                    f"snapshot directory already exists with different content: {snapshot_dir}"
                )
            return False

        _cleanup_staging()
        staging.mkdir(parents=True)
        _materialize_snapshot(
            staging,
            pages=pages,
            bundle=bundle,
            manifest=manifest,
            network=network,
            write_hook=write_hook,
        )
        # Atomic publish: staging → final (dest must not exist).
        os.replace(staging, snapshot_dir)
        return True
    except Exception:
        _cleanup_staging()
        raise
    finally:
        # Compare path / failed replace: never leave staging behind.
        _cleanup_staging()


def merge_catalog_atomic(
    catalog_path: Path,
    *,
    alias: str,
    label: str,
    dataset_id: str,
    content_hash: str,
    manifest_path: str,
    bundle_path: str,
    symbols: tuple[str, ...],
    time_range: dict[str, str],
) -> bool:
    """Atomically upsert catalog alias. Paths should be absolute for HL entries."""
    datasets: list[dict[str, Any]] = []
    if catalog_path.is_file():
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            datasets = [d for d in raw if isinstance(d, dict)]
        elif isinstance(raw, dict):
            datasets = [d for d in raw.get("datasets", []) if isinstance(d, dict)]
        else:
            raise HlDatasetExportError("catalog root must be list or object with datasets")

    entry = {
        "id": alias,
        "label": label,
        "dataset_id": dataset_id,
        "content_hash": content_hash,
        "manifest_path": manifest_path,
        "bundle_path": bundle_path,
        "symbols": list(symbols),
        "time_range": time_range,
    }
    replaced = False
    new_datasets: list[dict[str, Any]] = []
    for row in datasets:
        if str(row.get("id")) == alias:
            new_datasets.append(entry)
            replaced = True
        else:
            new_datasets.append(row)
    if not replaced:
        new_datasets.append(entry)

    new_datasets.sort(key=lambda r: str(r.get("id", "")))
    text = dumps_deterministic({"datasets": new_datasets})
    _atomic_write_text(catalog_path, text)
    return True


def production_env_snippet(*, artifacts_root: Path, catalog_path: Path) -> str:
    root = artifacts_root.as_posix()
    cat = catalog_path.as_posix()
    return (
        "RESEARCH_REPO_ROOT=/app\n"
        f"RESEARCH_ARTIFACTS_ROOT={root}\n"
        f"RESEARCH_DATASET_CATALOG_PATH={cat}\n"
    )


def export_from_raw_pages(
    pages: tuple[bytes, ...],
    *,
    out_root: Path,
    catalog_path: Path,
    window: ExportWindow,
    code_commit: str,
    symbol: MarketSymbol = MarketSymbol.BTC,
    network: HyperliquidNetwork = HyperliquidNetwork.MAINNET,
    catalog_alias: str | None = None,
    catalog_label: str | None = None,
    path_style: str = "absolute",
    write_hook: SnapshotWriteHook | None = None,
) -> ExportResult:
    """Offline/online shared path: raw pages → quality → snapshot → catalog."""
    if not pages:
        raise HlDatasetExportError("no raw pages to export")

    alias = catalog_alias or default_catalog_alias(symbol, network, window.days)
    evaluation_time = window.end_close + timedelta(seconds=1)
    raws = raw_candles_from_hl_pages(pages, symbol=symbol, evaluation_time=evaluation_time)
    window_raws = tuple(
        r
        for r in raws
        if window.start_open <= daily_open(r.open_time) <= daily_open(window.end_close)
    )
    daily = normalize_batch(window_raws, evaluation_time=evaluation_time)
    daily = sort_candles(daily)
    assert_daily_window(daily, window, symbol=symbol)

    bundle = build_research_bundle(daily, symbol=symbol, evaluation_time=evaluation_time)
    quality_summary = require_quality_valid(bundle, symbol=symbol, evaluation_time=evaluation_time)

    source = f"hyperliquid/{network.value}"
    symbols = (symbol.value,)
    raw_content_hash = hash_raw_bytes(b"".join(pages))
    raw_dataset_id = derive_dataset_id(
        raw_content_hash, SCHEMA_VERSION, raw_source_for_network(network)
    )
    import_configuration = {
        "provider": PROVIDER_VERSION,
        "network": network.value,
        "symbol": symbol.value,
        "timeframe": "1D",
        "days": window.days,
        "as_of": window.as_of.isoformat().replace("+00:00", "+00:00"),
        "end_date": window.end_date.isoformat(),
        "start_open": window.start_open.isoformat().replace("+00:00", "+00:00"),
        "end_close": window.end_close.isoformat().replace("+00:00", "+00:00"),
        "aggregation": "weekly_monthly_from_daily",
        "fetch": "fetch_candles",
    }
    manifest = build_export_manifest(
        bundle=bundle,
        symbols=symbols,
        window=window,
        source=source,
        raw_content_hash=raw_content_hash,
        raw_dataset_id=raw_dataset_id,
        import_configuration=import_configuration,
        quality_summary=quality_summary,
        code_commit=code_commit,
    )
    dataset_id = manifest.dataset_id
    if not dataset_id:
        raise HlDatasetExportError("dataset_id missing after parse_manifest")

    out_root = out_root.resolve()
    snapshot_dir = out_root / dataset_id
    wrote = write_snapshot_if_absent(
        snapshot_dir,
        pages=pages,
        bundle=bundle,
        manifest=manifest,
        network=network,
        write_hook=write_hook,
    )

    # Verify raw index identity matches manifest (network-aware).
    index = json.loads((snapshot_dir / "raw" / "index.json").read_text(encoding="utf-8"))
    if index.get("raw_dataset_id") != raw_dataset_id:
        raise HlDatasetExportError("raw_dataset_id mismatch between index and manifest")
    if index.get("source") != raw_source_for_network(network):
        raise HlDatasetExportError("raw source mismatch between index and network")

    manifest_file = snapshot_dir / "dataset_manifest.json"
    bundle_file = snapshot_dir / "bundle.json"
    if path_style == "absolute":
        manifest_ref = str(manifest_file.resolve())
        bundle_ref = str(bundle_file.resolve())
    elif path_style == "relative":
        manifest_ref = manifest_file.relative_to(out_root).as_posix()
        bundle_ref = bundle_file.relative_to(out_root).as_posix()
    else:
        raise HlDatasetExportError(f"unknown path_style {path_style!r}")

    label = catalog_label or (
        f"Hyperliquid {symbol.value} {network.value} {window.days}d "
        f"(as-of {window.end_date.isoformat()})"
    )
    merge_catalog_atomic(
        catalog_path.resolve(),
        alias=alias,
        label=label,
        dataset_id=dataset_id,
        content_hash=manifest.content_hash,
        manifest_path=manifest_ref,
        bundle_path=bundle_ref,
        symbols=symbols,
        time_range={
            "start": window.start_timestamp.isoformat().replace("+00:00", "+00:00"),
            "end": window.end_timestamp.isoformat().replace("+00:00", "+00:00"),
        },
    )

    return ExportResult(
        dataset_id=dataset_id,
        content_hash=manifest.content_hash,
        raw_content_hash=raw_content_hash,
        snapshot_dir=snapshot_dir,
        catalog_path=catalog_path.resolve(),
        catalog_alias=alias,
        daily_count=len(bundle.daily.get(symbol.value, ())),
        weekly_count=len(bundle.weekly.get(symbol.value, ())),
        monthly_count=len(bundle.monthly.get(symbol.value, ())),
        wrote_snapshot=wrote,
        catalog_updated=True,
        code_commit=code_commit,
    )


async def fetch_raw_pages(
    *,
    symbol: MarketSymbol,
    window: ExportWindow,
    network: HyperliquidNetwork = HyperliquidNetwork.MAINNET,
) -> tuple[bytes, ...]:
    """Live fetch via ``fetch_candles`` (not ``fetch_history``); capture page bytes."""
    config = HyperliquidPublicConfig.for_network(network)
    client = HyperliquidHttpClient(config)
    try:
        provider = HyperliquidHistoricalProvider(client, config)
        evaluation_time = window.end_close + timedelta(seconds=1)
        _candles, pages = await provider.fetch_candles_with_raw_pages(
            symbol,
            MarketTimeframe.DAILY,
            window.start_open,
            window.end_close,
            evaluation_time,
        )
        return pages
    finally:
        await client.aclose()


def synthesize_hl_daily_pages(
    *,
    start_open: datetime,
    days: int,
    symbol: MarketSymbol = MarketSymbol.BTC,
    base_price: Decimal = Decimal("40000"),
) -> tuple[bytes, ...]:
    """Build one candleSnapshot page with non-flat volatile closes (CI fixture)."""
    from market_data.providers.hyperliquid import coin_for_symbol, interval_for_timeframe

    coin = coin_for_symbol(symbol)
    interval = interval_for_timeframe(MarketTimeframe.DAILY)
    rows: list[dict[str, object]] = []
    for i in range(days):
        open_time = ensure_utc(start_open) + timedelta(days=i)
        close_time = daily_close(open_time)
        wave = Decimal(i % 17) - Decimal("8")
        drift = Decimal(i) * Decimal("3.5")
        o = (base_price + drift + wave * Decimal("25")).quantize(Decimal("0.01"))
        c = (o + wave * Decimal("12.5") + Decimal("5")).quantize(Decimal("0.01"))
        h = max(o, c) + Decimal("40")
        low = min(o, c) - Decimal("35")
        vol = Decimal("1000") + Decimal(i) * Decimal("3")
        rows.append(
            {
                "s": coin,
                "i": interval,
                "t": int(open_time.timestamp() * 1000),
                "T": int(close_time.timestamp() * 1000),
                "o": format(o, "f"),
                "h": format(h, "f"),
                "l": format(low, "f"),
                "c": format(c, "f"),
                "v": format(vol, "f"),
                "n": 100 + i,
            }
        )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    return (payload.encode("utf-8"),)


__all__ = [
    "DEFAULT_DAYS",
    "ExportResult",
    "ExportWindow",
    "HlDatasetExportError",
    "assert_daily_window",
    "build_export_manifest",
    "build_research_bundle",
    "default_catalog_alias",
    "dumps_deterministic",
    "export_from_raw_pages",
    "fetch_raw_pages",
    "last_closed_utc_day",
    "merge_catalog_atomic",
    "parse_as_of",
    "production_env_snippet",
    "raw_source_for_network",
    "require_quality_valid",
    "resolve_export_code_commit",
    "resolve_export_window",
    "synthesize_hl_daily_pages",
    "write_raw_pages",
    "write_snapshot_if_absent",
]
