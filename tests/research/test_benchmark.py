"""Tests for benchmark calculation (#144)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from backtester.models import HistoricalDataBundle
from research.benchmark import compute_benchmark_result, compute_buy_and_hold_return
from research.experiment_spec import parse_experiment_spec
from strategy_engine.models import Candle, Timeframe

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def _daily(symbol: str, day: int, close: str) -> Candle:
    open_time = datetime(2024, 1, day, tzinfo=UTC)
    p = Decimal(close)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.DAILY,
        open_time=open_time,
        close_time=open_time.replace(hour=23, minute=59, second=59),
        open=p,
        high=p,
        low=p,
        close=p,
        volume=Decimal("1"),
        is_closed=True,
    )


def _btc_spec(**overrides: object):
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["symbols"] = ["BTC"]
    raw.update(overrides)
    return parse_experiment_spec(raw)


def _bundle(*closes: str) -> HistoricalDataBundle:
    candles = tuple(_daily("BTC", i + 1, c) for i, c in enumerate(closes))
    return HistoricalDataBundle(
        daily={"BTC": candles},
        weekly={"BTC": ()},
        monthly={"BTC": ()},
    )


def test_buy_and_hold_return() -> None:
    assert compute_buy_and_hold_return(_bundle("100", "110"), "BTC") == Decimal("0.1")


def test_compute_benchmark_from_example_spec() -> None:
    ref, result = compute_benchmark_result(_btc_spec(), _bundle("100", "125"))
    assert "buy_and_hold" in ref.benchmark_id.lower()
    assert result == Decimal("0.25")
    assert ref.cost_parity is True


def test_unsupported_benchmark_fails() -> None:
    with pytest.raises(ValueError, match="unsupported benchmark"):
        compute_benchmark_result(
            _btc_spec(benchmark="sharpe_oracle"),
            _bundle("100", "110"),
        )
