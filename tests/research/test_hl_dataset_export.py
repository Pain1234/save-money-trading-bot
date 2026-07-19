"""Offline tests for Hyperliquid → Research Lab catalog export (#274)."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from market_data.config import HyperliquidNetwork
from market_data.content_hash import derive_dataset_id
from market_data.models import MarketSymbol
from research.dataset_binding import bind_dataset_to_bundle
from research.experiment_spec import parse_experiment_spec
from research.hl_dataset_export import (
    DEFAULT_DAYS,
    SCHEMA_VERSION,
    HlDatasetExportError,
    default_catalog_alias,
    export_from_raw_pages,
    normalize_git_sha,
    parse_as_of,
    raw_source_for_network,
    resolve_export_code_commit,
    resolve_export_window,
    synthesize_hl_daily_pages,
)
from research.write_service import load_dataset_catalog

_FIXED_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _jan_2024_window(*, days: int = 31):
    as_of = parse_as_of("2024-01-31T23:59:59+00:00")
    return resolve_export_window(as_of=as_of, days=days)


def _export(
    pages: tuple[bytes, ...],
    *,
    out_root: Path,
    catalog_path: Path,
    window,
    **kwargs,
):
    return export_from_raw_pages(
        pages,
        out_root=out_root,
        catalog_path=catalog_path,
        window=window,
        code_commit=_FIXED_COMMIT,
        path_style="absolute",
        **kwargs,
    )


def test_resolve_window_excludes_open_day() -> None:
    window = resolve_export_window(as_of=datetime(2024, 2, 1, 12, 0, 0, tzinfo=UTC), days=31)
    assert window.end_date.isoformat() == "2024-01-31"
    assert window.days == 31
    assert window.start_open == datetime(2024, 1, 1, tzinfo=UTC)


def test_default_alias_derives_from_symbol_network_days() -> None:
    assert (
        default_catalog_alias(MarketSymbol.BTC, HyperliquidNetwork.MAINNET, 730)
        == "hl-btc-mainnet-730d"
    )
    assert (
        default_catalog_alias(MarketSymbol.ETH, HyperliquidNetwork.TESTNET, 31)
        == "hl-eth-testnet-31d"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-sha",
        "unknown",
        "1234567",
        "abcdef0",
        "0123456789abcdef0123456789abcdef0123456",  # 39 hex
        "0123456789abcdef0123456789abcdef012345678",  # 41 hex
        "g123456789abcdef0123456789abcdef01234567",  # non-hex
    ],
)
def test_normalize_git_sha_rejects_invalid(bad: str) -> None:
    with pytest.raises(HlDatasetExportError, match="full git SHA"):
        normalize_git_sha(bad)
    with pytest.raises(HlDatasetExportError, match="full git SHA"):
        resolve_export_code_commit(explicit=bad, repo_root=Path("."))


def test_normalize_git_sha_accepts_full_hex_and_lowercases() -> None:
    upper = "0123456789ABCDEF0123456789ABCDEF01234567"
    assert normalize_git_sha(upper) == _FIXED_COMMIT
    sha256 = "a" * 64
    assert normalize_git_sha(sha256) == sha256
    assert resolve_export_code_commit(explicit=f"  {upper}  ", repo_root=Path(".")) == (
        _FIXED_COMMIT
    )


def test_export_offline_full_month_iso_weeks(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = _export(pages, out_root=out_root, catalog_path=catalog_path, window=window)
    assert result.catalog_alias == "hl-btc-mainnet-31d"
    assert result.daily_count == 31
    assert result.weekly_count == 4
    assert result.monthly_count == 1
    assert result.wrote_snapshot is True
    assert result.code_commit == _FIXED_COMMIT
    assert (result.snapshot_dir / "bundle.json").is_file()
    assert (result.snapshot_dir / "dataset_manifest.json").is_file()
    assert (result.snapshot_dir / "raw" / "index.json").is_file()

    manifest = json.loads(
        (result.snapshot_dir / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["code_commit"] == _FIXED_COMMIT
    assert not manifest["code_commit"].startswith("hlxprt-")

    bundle = json.loads((result.snapshot_dir / "bundle.json").read_text(encoding="utf-8"))
    closes = [Decimal(str(c["close"])) for c in bundle["daily"]["BTC"]]
    assert len(set(closes)) > 1

    again = _export(pages, out_root=out_root, catalog_path=catalog_path, window=window)
    assert again.dataset_id == result.dataset_id
    assert again.wrote_snapshot is False
    assert again.content_hash == result.content_hash


def test_export_offline_730_days(tmp_path: Path) -> None:
    # Pin end so the 730d window is fully determined.
    as_of = parse_as_of("2024-12-31T23:59:59+00:00")
    window = resolve_export_window(as_of=as_of, days=DEFAULT_DAYS)
    assert window.days == 730
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = _export(pages, out_root=out_root, catalog_path=catalog_path, window=window)
    assert result.catalog_alias == "hl-btc-mainnet-730d"
    assert result.daily_count == 730
    assert result.weekly_count > 0
    assert result.monthly_count > 0
    # Gapless bounds
    daily = json.loads((result.snapshot_dir / "bundle.json").read_text(encoding="utf-8"))["daily"][
        "BTC"
    ]
    assert daily[0]["open_time"].startswith(window.start_open.date().isoformat())
    assert daily[-1]["open_time"].startswith(window.end_date.isoformat())


def test_gap_fails_and_leaves_catalog_unchanged(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    payload = json.loads(pages[0].decode("utf-8"))
    del payload[10]
    gapped = (json.dumps(payload, separators=(",", ":")).encode("utf-8"),)

    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
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
        _export(
            gapped,
            out_root=out_root,
            catalog_path=catalog_path,
            window=window,
        )
    assert catalog_path.read_text(encoding="utf-8") == before
    assert not any(p for p in out_root.iterdir() if p.is_dir() and not p.name.startswith("."))


def test_partial_snapshot_failure_leaves_no_final_or_catalog(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"

    def boom(_staging: Path) -> None:
        raise OSError("injected disk full after raw pages")

    with pytest.raises(OSError, match="injected disk full"):
        _export(
            pages,
            out_root=out_root,
            catalog_path=catalog_path,
            window=window,
            write_hook=boom,
        )
    assert not catalog_path.exists()
    leftovers = [p for p in out_root.iterdir()] if out_root.exists() else []
    assert not any(p.is_dir() and not p.name.startswith(".") for p in leftovers)
    assert not any(p.name.endswith(".write." + str(p.stat().st_mtime)) for p in leftovers)
    # No lingering staging dirs.
    assert not any(".write." in p.name for p in leftovers)


def test_catalog_load_and_bind_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = _export(pages, out_root=out_root, catalog_path=catalog_path, window=window)

    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.delenv("RESEARCH_DATASET_CATALOG_JSON", raising=False)
    entries = load_dataset_catalog()
    by_id = {e.id: e for e in entries}
    assert "hl-btc-mainnet-31d" in by_id
    entry = by_id["hl-btc-mainnet-31d"]
    assert entry.dataset_id == result.dataset_id
    assert entry.content_hash == result.content_hash
    assert Path(entry.bundle_path).is_absolute()

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
            "symbol_constraints": {
                "BTC": {
                    "quantity_step": "0.00001",
                    "minimum_quantity": "0.00001",
                    "minimum_notional": "10",
                    "price_tick_size": "0.1",
                }
            },
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


def test_testnet_raw_identity_differs_from_mainnet(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    main = _export(
        pages,
        out_root=out_root,
        catalog_path=out_root / "catalog-main.json",
        window=window,
        network=HyperliquidNetwork.MAINNET,
    )
    test = _export(
        pages,
        out_root=out_root,
        catalog_path=out_root / "catalog-test.json",
        window=window,
        network=HyperliquidNetwork.TESTNET,
    )
    assert main.catalog_alias == "hl-btc-mainnet-31d"
    assert test.catalog_alias == "hl-btc-testnet-31d"
    main_index = json.loads((main.snapshot_dir / "raw" / "index.json").read_text(encoding="utf-8"))
    test_index = json.loads((test.snapshot_dir / "raw" / "index.json").read_text(encoding="utf-8"))
    assert main_index["source"] == "hyperliquid/mainnet/raw"
    assert test_index["source"] == "hyperliquid/testnet/raw"
    assert main_index["raw_dataset_id"] != test_index["raw_dataset_id"]
    assert main_index["raw_dataset_id"] == derive_dataset_id(
        main.raw_content_hash, SCHEMA_VERSION, raw_source_for_network(HyperliquidNetwork.MAINNET)
    )
    assert test_index["raw_dataset_id"] == derive_dataset_id(
        test.raw_content_hash, SCHEMA_VERSION, raw_source_for_network(HyperliquidNetwork.TESTNET)
    )
    # Same candle bytes → same content_hash (normalized), different dataset_id via source.
    assert main.content_hash == test.content_hash
    assert main.dataset_id != test.dataset_id


def test_divergent_snapshot_fail_closed(tmp_path: Path) -> None:
    window = _jan_2024_window(days=31)
    pages = synthesize_hl_daily_pages(
        start_open=window.start_open, days=window.days, symbol=MarketSymbol.BTC
    )
    out_root = tmp_path / "research"
    catalog_path = out_root / "catalog.json"
    result = _export(pages, out_root=out_root, catalog_path=catalog_path, window=window)
    bundle_path = result.snapshot_dir / "bundle.json"
    bundle_path.write_text(bundle_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(HlDatasetExportError, match="different content"):
        _export(pages, out_root=out_root, catalog_path=catalog_path, window=window)


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
            "--code-commit",
            _FIXED_COMMIT,
            "--out-root",
            str(out_root),
            "--catalog-path",
            str(catalog_path),
        ]
    )
    assert code == 0
    assert catalog_path.is_file()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["datasets"][0]["id"] == "hl-btc-mainnet-31d"
