# ruff: noqa: E402
"""Deterministic soak candle generation and invariant checks."""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[3] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from backtester.models import HistoricalDataBundle
from strategy_engine.models import Candle

from tests.strategy_engine.conftest import (
    build_rising_monthly_series,
    build_rising_weekly_series,
    dt,
    make_daily_candle,
)

SYMBOLS = ("BTC", "ETH", "SOL")


@dataclass(frozen=True)
class SoakMetrics:
    days: int
    evaluations: int
    intents: int
    fills: int
    stop_updates: int
    audit_events: int
    elapsed_seconds: float


def generate_soak_bundle(*, days: int, seed: int) -> HistoricalDataBundle:
    rng = random.Random(seed)
    daily: dict[str, tuple[Candle, ...]] = {}
    for symbol in SYMBOLS:
        candles: list[Candle] = []
        price = Decimal("100")
        start = dt(2024, 1, 1)
        for i in range(days):
            open_time = start + timedelta(days=i)
            drift = Decimal(str(rng.randint(-3, 5)))
            close = price + drift
            high = max(price, close) + Decimal(str(rng.randint(0, 2)))
            low = min(price, close) - Decimal(str(rng.randint(0, 2)))
            if i == 29:
                close = Decimal("125")
                high = Decimal("130")
            candles.append(
                make_daily_candle(
                    symbol,
                    open_time,
                    str(price),
                    str(high),
                    str(low),
                    str(close),
                    vol=str(1000 + rng.randint(0, 500)),
                )
            )
            price = close
        daily[symbol] = tuple(candles)
    weekly = {s: build_rising_weekly_series(s, 60).candles for s in SYMBOLS}
    monthly = {s: build_rising_monthly_series(s, 30).candles for s in SYMBOLS}
    return HistoricalDataBundle(daily=daily, weekly=weekly, monthly=monthly)


def assert_soak_invariants(repo: object) -> None:
    from paper_trading.repository import PaperTradingRepository

    assert isinstance(repo, PaperTradingRepository)
    open_positions = repo.get_open_positions()
    by_symbol: dict[str, int] = {}
    for pos in open_positions:
        by_symbol[pos.symbol] = by_symbol.get(pos.symbol, 0) + 1
        assert pos.quantity > 0
        assert pos.margin_reserved >= 0
        assert pos.current_stop >= pos.initial_stop
    assert all(count <= 1 for count in by_symbol.values())
    assert len(open_positions) <= 3
    for fill in repo.list_all_fills():
        assert fill.quantity > 0
        assert fill.fill_price > 0
    keys = [f.deterministic_fill_key for f in repo.list_all_fills()]
    assert len(keys) == len(set(keys))
