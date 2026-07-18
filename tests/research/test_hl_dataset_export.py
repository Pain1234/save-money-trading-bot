"""Offline tests for Hyperliquid → Research Lab catalog export (#274)."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from market_data.models import MarketSymbol
from research.dataset_binding import bind_dataset_to_bundle
from research.experiment_spec import parse_experiment_spec
from research.hl_dataset_export import (
    HlDatasetExportError,
    export_from_raw_pages,
    parse_as_of,
    resolve_export_window,
    synthesize_hl_daily_pages,
)
from research.write_service import load_dataset_catalog


def _jan_2024_window(*, days: int = 31):
    # 2024-01-31 fully closed → pin end of that day.
    as_of = parse_as_of("2024-01-31T23:59:59+00:00")
    return resolve_export_window(as_of=as_of, days=days)


def test_resolve_window_excludes_open_day() -> None:
    # Mid-day 2024-02-01 → last closed is 2024-01-31.
    window = resolve_export_window(as_of=datetime(2024, 2, 1, 12, 0, 0, tzinfo=UTC), days=31)
    assert window.end_date.isoformat() == "2024-01-31"
    assert window.days == 31
    assert window.start_open == datetime(2024, 1, 1, tzinfo=UTC)


def test_export_offline_full_month_iso_weeks(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = export_from_raw_pages(
        pages,
        out_root=out_root,
        catalog_path=catalog_path,
        window=window,
        catalog_alias="hl-btc-mainnet-730d",
        path_style="absolute",
    )
    assert result.daily_count == 31
    assert result.weekly_count == 4  # Jan 1 is Monday; weeks through Jan 28
    assert result.monthly_count == 1
    assert result.wrote_snapshot is True
    assert (result.snapshot_dir / "bundle.json").is_file()
    assert (result.snapshot_dir / "dataset_manifest.json").is_file()
    assert (result.snapshot_dir / "raw" / "index.json").is_file()

    bundle = json.loads((result.snapshot_dir / "bundle.json").read_text(encoding="utf-8"))
    closes = [Decimal(str(c["close"])) for c in bundle["daily"]["BTC"]]
    assert len(set(closes)) > 1
    assert Decimal("100") not in closes or len(set(closes)) > 1

    # Byte-identical re-export
    again = export_from_raw_pages(
        pages,
        out_root=out_root,
        catalog_path=catalog_path,
        window=window,
        catalog_alias="hl-btc-mainnet-730d",
        path_style="absolute",
    )
    assert again.dataset_id == result.dataset_id
    assert again.wrote_snapshot is False
    assert again.content_hash == result.content_hash


def test_gap_fails_and_leaves_catalog_unchanged(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    # Drop one candle from the JSON list (create a gap).
    payload = json.loads(pages[0].decode("utf-8"))
    del payload[10]
    gapped = (json.dumps(payload, separators=(",", ":")).encode("utf-8"),)

    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    # Seed a catalog that must remain untouched on failure.
    seed = {
        "datasets": [
            {
                "id": "keep-me",
                "label": "keep",
                "dataset_id": "abc",
                "content_hash": "0" * 64,
                "manifest_path": "x",
                "bundle_path": "y",
                "symbols": ["BTC"],
            }
        ]
    }
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    before = catalog_path.read_text(encoding="utf-8")

    with pytest.raises(HlDatasetExportError):
        export_from_raw_pages(
            gapped,
            out_root=out_root,
            catalog_path=catalog_path,
            window=window,
            catalog_alias="hl-btc-mainnet-730d",
            path_style="absolute",
        )
    assert catalog_path.read_text(encoding="utf-8") == before
    assert not any(out_root.glob("*/bundle.json"))


def test_catalog_load_and_bind_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = export_from_raw_pages(
        pages,
        out_root=out_root,
        catalog_path=catalog_path,
        window=window,
        catalog_alias="hl-btc-mainnet-730d",
        path_style="absolute",
    )

    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.delenv("RESEARCH_DATASET_CATALOG_JSON", raising=False)
    entries = load_dataset_catalog()
    by_id = {e.id: e for e in entries}
    assert "hl-btc-mainnet-730d" in by_id
    entry = by_id["hl-btc-mainnet-730d"]
    assert entry.dataset_id == result.dataset_id
    assert entry.content_hash == result.content_hash
    assert Path(entry.bundle_path).is_absolute()
    assert Path(entry.manifest_path).is_absolute()

    from backtester.models import HistoricalDataBundle

    hist = HistoricalDataBundle.model_validate(
        json.loads(Path(entry.bundle_path).read_text(encoding="utf-8"))
    )
    spec = parse_experiment_spec(
        {
            "schema_version": "1.0",
            "hypothesis": "bind smoke",
            "strategy_version": "1.0.0",
            "parameters": {},
            "dataset_manifest_ref": {
                "dataset_id": entry.dataset_id,
                "content_hash": entry.content_hash,
                "manifest_path": entry.manifest_path,
            },
            "symbols": ["BTC"],
            "time_range": {
                "start": window.start_timestamp.isoformat().replace("+00:00", "+00:00"),
                "end": window.end_timestamp.isoformat().replace("+00:00", "+00:00"),
            },
            "starting_capital": "100000",
            "fee_assumption": {
                "entry_fee_rate": "0.0002",
                "exit_fee_rate": "0.0002",
            },
            "slippage_assumption": {"slippage_bps": "1"},
            "funding_assumption": {"enabled": False},
            "benchmark": "buy_and_hold",
            "owner": "test",
        }
    )
    manifest, filtered, content_hash = bind_dataset_to_bundle(spec, hist, repo_root=out_root)
    assert manifest.dataset_id == result.dataset_id
    assert content_hash == result.content_hash
    assert filtered.daily["BTC"]


def test_divergent_snapshot_fail_closed(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = export_from_raw_pages(
        pages,
        out_root=out_root,
        catalog_path=catalog_path,
        window=window,
        path_style="absolute",
    )
    # Corrupt existing snapshot.
    bundle_path = result.snapshot_dir / "bundle.json"
    bundle_path.write_text(bundle_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(HlDatasetExportError, match="different content"):
        export_from_raw_pages(
            pages,
            out_root=out_root,
            catalog_path=catalog_path,
            window=window,
            path_style="absolute",
        )


def test_cli_offline_synthetic(tmp_path: Path) -> None:
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "export_research_dataset_hyperliquid.py"
    )
    ns = runpy.run_path(str(script))
    main = ns["main"]
    code = main(
        [
            "--end-date",
            "2024-01-31",
            "--days",
            "31",
            "--offline-synthetic",
            "--out-root",
            str(out_root),
            "--catalog-path",
            str(catalog_path),
        ]
    )
    assert code == 0
    assert catalog_path.is_file()
