#!/usr/bin/env python3
"""Export Hyperliquid BTC candles into a versioned Research Lab catalog (#274).

Fetches via ``fetch_candles`` (not ``fetch_history``), persists immutable raw
HTTP page bytes, builds D/W/M bundle + DatasetManifest, and atomically updates
``catalog.json``. Does not import into Postgres.

Usage (from repo root, venv active)::

    python scripts/export_research_dataset_hyperliquid.py \\
        --end-date 2024-01-31 --days 31 \\
        --out-root /data/research \\
        --catalog-path /data/research/catalog.json

Offline / CI (synthetic volatile pages, no network)::

    python scripts/export_research_dataset_hyperliquid.py \\
        --end-date 2024-01-31 --days 31 --offline-synthetic \\
        --out-root ./artifacts/research-datasets \\
        --catalog-path ./artifacts/research-datasets/catalog.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_path() -> None:
    services = REPO_ROOT / "services"
    if str(services) not in sys.path:
        sys.path.insert(0, str(services))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Export Hyperliquid candles into Research Lab catalog (Issue #274)."
    )
    pin = p.add_mutually_exclusive_group(required=True)
    pin.add_argument(
        "--end-date",
        help="UTC calendar end pin (YYYY-MM-DD). Last closed day is derived from this date.",
    )
    pin.add_argument(
        "--as-of",
        help=(
            "UTC as-of pin (YYYY-MM-DD or ISO datetime). "
            "Last fully closed UTC day at this instant."
        ),
    )
    p.add_argument(
        "--days",
        type=int,
        default=730,
        help="Number of closed daily candles (default 730).",
    )
    p.add_argument(
        "--symbol",
        default="BTC",
        help="Market symbol (default BTC).",
    )
    p.add_argument(
        "--network",
        default="mainnet",
        choices=("mainnet", "testnet"),
        help="Hyperliquid public network (default mainnet).",
    )
    p.add_argument(
        "--out-root",
        type=Path,
        required=True,
        help="Artifacts root for versioned snapshots (e.g. /data/research).",
    )
    p.add_argument(
        "--catalog-path",
        type=Path,
        required=True,
        help="catalog.json path (e.g. /data/research/catalog.json).",
    )
    p.add_argument(
        "--catalog-alias",
        default="hl-btc-mainnet-730d",
        help="Catalog id alias (not the content dataset_id).",
    )
    p.add_argument(
        "--path-style",
        default="absolute",
        choices=("absolute", "relative"),
        help="Catalog path style (production: absolute under artifacts root).",
    )
    p.add_argument(
        "--offline-synthetic",
        action="store_true",
        help="Skip network; synthesize volatile HL-shaped raw pages for the window.",
    )
    p.add_argument(
        "--raw-pages-dir",
        type=Path,
        help="Optional directory of raw page_*.json / *.bin files (offline replay).",
    )
    return p


def _load_raw_pages_dir(path: Path) -> tuple[bytes, ...]:
    files = sorted(
        [
            *path.glob("page_*.json"),
            *path.glob("page_*.bin"),
            *path.glob("*.json"),
        ]
    )
    # Prefer page_* only when present.
    page_files = sorted(path.glob("page_*"))
    if page_files:
        files = page_files
    if not files:
        raise SystemExit(f"no raw page files under {path}")
    return tuple(f.read_bytes() for f in files)


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    from market_data.config import HyperliquidNetwork
    from market_data.models import MarketSymbol
    from research.hl_dataset_export import (
        DEFAULT_DAYS,
        HlDatasetExportError,
        export_from_raw_pages,
        fetch_raw_pages,
        parse_as_of,
        production_env_snippet,
        resolve_export_window,
        synthesize_hl_daily_pages,
    )

    args = build_parser().parse_args(argv)
    pin = args.as_of or args.end_date
    assert pin is not None
    as_of = parse_as_of(pin)
    # --end-date means that calendar day is the last closed day: pin as end of that day.
    if args.end_date and not args.as_of:
        d = as_of.date()
        as_of = parse_as_of(f"{d.isoformat()}T23:59:59+00:00")

    days = int(args.days)
    if days < 1:
        raise SystemExit("--days must be >= 1")

    window = resolve_export_window(as_of=as_of, days=days)
    symbol = MarketSymbol(args.symbol.upper())
    network = HyperliquidNetwork(args.network)

    if args.offline_synthetic and args.raw_pages_dir:
        raise SystemExit("use only one of --offline-synthetic / --raw-pages-dir")

    try:
        if args.offline_synthetic:
            pages = synthesize_hl_daily_pages(
                start_open=window.start_open, days=window.days, symbol=symbol
            )
        elif args.raw_pages_dir:
            pages = _load_raw_pages_dir(args.raw_pages_dir)
        else:
            pages = asyncio.run(fetch_raw_pages(symbol=symbol, window=window, network=network))

        result = export_from_raw_pages(
            pages,
            out_root=args.out_root,
            catalog_path=args.catalog_path,
            window=window,
            symbol=symbol,
            network=network,
            catalog_alias=args.catalog_alias,
            path_style=args.path_style,
        )
    except HlDatasetExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"dataset_id={result.dataset_id}")
    print(f"content_hash={result.content_hash}")
    print(f"raw_content_hash={result.raw_content_hash}")
    print(f"snapshot_dir={result.snapshot_dir}")
    print(f"catalog_path={result.catalog_path}")
    print(f"catalog_alias={result.catalog_alias}")
    print(
        f"counts daily={result.daily_count} weekly={result.weekly_count} "
        f"monthly={result.monthly_count}"
    )
    print(f"wrote_snapshot={result.wrote_snapshot}")
    print()
    print("# Production env (API service):")
    print(
        production_env_snippet(
            artifacts_root=args.out_root.resolve(),
            catalog_path=result.catalog_path,
        ),
        end="",
    )
    if days == DEFAULT_DAYS and args.catalog_alias == "hl-btc-mainnet-730d":
        print("# Alias hl-btc-mainnet-730d is a catalog id; dataset_id is content identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
