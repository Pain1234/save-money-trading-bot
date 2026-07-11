# ruff: noqa: E402
"""Shared fixtures for paper trading lifecycle tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from backtester.data import evaluation_time_for_daily
from market_data.models import (
    DataQualityReport,
    DataQualityStatus,
    MarketSymbol,
    StrategyDataBundle,
)
from strategy_engine.models import CandleSeries, Timeframe

from tests.backtester.conftest import make_daily


def utc_dt(y: int, m: int, d: int, h: int = 0, minute: int = 0, second: int = 5) -> datetime:
    return datetime(y, m, d, h, minute, second, tzinfo=UTC)


def daily_open(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def make_strategy_bundle(
    symbol: str = "BTC",
    *,
    evaluation_time: datetime | None = None,
    days: int = 30,
) -> StrategyDataBundle:
    candles = tuple(
        make_daily(symbol, daily_open(2024, 1, 1) + timedelta(days=i), "100", "105", "95", "100")
        for i in range(days)
    )
    last = candles[-1]
    evaluation_time = evaluation_time or evaluation_time_for_daily(last)
    daily = CandleSeries(symbol=symbol, timeframe=Timeframe.DAILY, candles=candles)
    weekly = CandleSeries(symbol=symbol, timeframe=Timeframe.WEEKLY, candles=candles[:4])
    monthly = CandleSeries(symbol=symbol, timeframe=Timeframe.MONTHLY, candles=candles[:2])
    return StrategyDataBundle(
        symbol=MarketSymbol(symbol),
        evaluation_time=evaluation_time,
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        report=DataQualityReport(
            status=DataQualityStatus.VALID,
            reason_codes=(),
            evaluation_time=evaluation_time,
        ),
    )
