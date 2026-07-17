"""Run-bound chart payload for Research Workspace (#266).

Written at finalize from the exact filtered HistoricalDataBundle used by the
backtest — not from live market data or a different dataset version.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from backtester.models import HistoricalDataBundle
from strategy_engine.models import Candle

from research.experiment_spec import ExperimentSpec

CHART_DATA_SCHEMA_VERSION = "1.0"


def _dec(value: Decimal | Any) -> str:
    return str(value)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _candle_row(candle: Candle) -> dict[str, str]:
    return {
        "time": _iso(candle.open_time),
        "open": _dec(candle.open),
        "high": _dec(candle.high),
        "low": _dec(candle.low),
        "close": _dec(candle.close),
        "volume": _dec(candle.volume),
    }


def _series_for_symbol(
    bundle: HistoricalDataBundle,
    symbol: str,
) -> list[dict[str, str]]:
    raw = bundle.daily.get(symbol)
    if raw is None:
        return []
    rows: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, Candle):
            rows.append(_candle_row(item))
        elif isinstance(item, dict):
            rows.append(
                {
                    "time": str(item.get("open_time") or item.get("time") or ""),
                    "open": str(item["open"]),
                    "high": str(item["high"]),
                    "low": str(item["low"]),
                    "close": str(item["close"]),
                    "volume": str(item.get("volume", "0")),
                }
            )
        else:
            # Pydantic-model-like
            rows.append(
                {
                    "time": _iso(item.open_time),
                    "open": _dec(item.open),
                    "high": _dec(item.high),
                    "low": _dec(item.low),
                    "close": _dec(item.close),
                    "volume": _dec(item.volume),
                }
            )
    return rows


def build_chart_data(
    spec: ExperimentSpec,
    bundle: HistoricalDataBundle,
    *,
    dataset_content_hash: str,
) -> dict[str, Any]:
    """Slim per-run OHLCV for symbols in the experiment (daily timeframe)."""
    symbols = [s.value if hasattr(s, "value") else str(s) for s in spec.symbols]
    by_symbol: dict[str, list[dict[str, str]]] = {}
    for symbol in symbols:
        by_symbol[symbol] = _series_for_symbol(bundle, symbol)
    return {
        "schema_version": CHART_DATA_SCHEMA_VERSION,
        "dataset_id": spec.dataset_manifest_ref.dataset_id,
        "dataset_content_hash": dataset_content_hash,
        "timeframe": "1D",
        "time_range": {
            "start": spec.time_range.start.isoformat(),
            "end": spec.time_range.end.isoformat(),
        },
        "symbols": by_symbol,
    }
