"""Shared research test fixtures with bound DatasetManifest (#163)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backtester.models import HistoricalDataBundle
from research.dataset_binding import build_manifest_dict_for_bundle
from research.experiment_spec import ExperimentSpec, TimeRange, parse_experiment_spec
from strategy_engine.models import Candle, Timeframe

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def candle(symbol: str, day: int, price: str = "100", month: int = 1) -> Candle:
    open_time = datetime(2024, month, day, tzinfo=UTC)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.DAILY,
        open_time=open_time,
        close_time=open_time.replace(hour=23, minute=59, second=59),
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=Decimal("1000"),
        is_closed=True,
    )


def btc_bundle(*, end_day: int = 28, price: str = "100") -> HistoricalDataBundle:
    symbol = "BTC"
    daily = tuple(candle(symbol, d, price=price) for d in range(1, end_day + 1))
    weekly = (
        Candle(
            symbol=symbol,
            timeframe=Timeframe.WEEKLY,
            open_time=datetime(2023, 12, 25, tzinfo=UTC),
            close_time=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),
            open=Decimal(price),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal(price),
            volume=Decimal("5000"),
            is_closed=True,
        ),
    )
    monthly = (
        Candle(
            symbol=symbol,
            timeframe=Timeframe.MONTHLY,
            open_time=datetime(2023, 12, 1, tzinfo=UTC),
            close_time=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),
            open=Decimal(price),
            high=Decimal(price),
            low=Decimal(price),
            close=Decimal(price),
            volume=Decimal("20000"),
            is_closed=True,
        ),
    )
    return HistoricalDataBundle(
        daily={symbol: daily},
        weekly={symbol: weekly},
        monthly={symbol: monthly},
        funding={symbol: ()},
    )


def research_time_range() -> TimeRange:
    return TimeRange(
        start=datetime(2023, 12, 1, tzinfo=UTC),
        end=datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC),
    )


def align_spec_to_bundle(
    tmp_path: Path,
    bundle: HistoricalDataBundle,
    *,
    symbols: list[str] | None = None,
    time_range: TimeRange | None = None,
    price_note: str = "",
) -> ExperimentSpec:
    """Write a matching DatasetManifest and return Spec bound to it."""
    symbols = symbols or ["BTC"]
    tr = time_range or research_time_range()
    manifest_path = tmp_path / f"dataset_manifest{price_note}.json"
    payload = build_manifest_dict_for_bundle(
        bundle=bundle,
        symbols=tuple(symbols),
        time_range=tr,
    )
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    data = deepcopy(json.loads(EXAMPLE_JSON.read_text(encoding="utf-8")))
    data["symbols"] = symbols
    data["time_range"] = {
        "start": tr.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "end": tr.end.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    data["dataset_manifest_ref"] = {
        "dataset_id": payload["dataset_id"],
        "content_hash": payload["content_hash"],
        "manifest_path": str(manifest_path.relative_to(REPO_ROOT))
        if manifest_path.is_relative_to(REPO_ROOT)
        else str(manifest_path),
    }
    # Prefer absolute path for tmp manifests outside repo.
    if not manifest_path.is_relative_to(REPO_ROOT):
        data["dataset_manifest_ref"]["manifest_path"] = str(manifest_path)
    data["benchmark"] = f"buy_and_hold_{symbols[0]}"
    return parse_experiment_spec(data)
