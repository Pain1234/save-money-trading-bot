"""Helpers for production lifecycle integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from backtester.models import HistoricalDataBundle
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.timeframes import ensure_utc
from paper_trading.controlled_market_data import ControlledMarketDataRuntime
from risk_engine.models import SymbolConstraints
from strategy_engine.models import Candle

from tests.paper_trading.conftest_execution import DEFAULT_CONSTRAINTS


def btc_eth_sol_constraints() -> dict[str, SymbolConstraints]:
    return {sym: DEFAULT_CONSTRAINTS for sym in ("BTC", "ETH", "SOL")}


def candle_to_normalized(candle: Candle) -> NormalizedCandle:
    tf = MarketTimeframe(candle.timeframe.value)
    return NormalizedCandle(
        symbol=MarketSymbol(candle.symbol),
        timeframe=tf,
        open_time=ensure_utc(candle.open_time),
        close_time=ensure_utc(candle.close_time),
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        is_closed=candle.is_closed,
    )


def ingest_historical_bundle(
    runtime: ControlledMarketDataRuntime,
    bundle: HistoricalDataBundle,
    symbol: str,
    *,
    daily_count: int | None = None,
    evaluation_time: datetime,
) -> None:
    dailies = bundle.daily[symbol]
    if daily_count is not None:
        dailies = dailies[:daily_count]
    normalized: list[NormalizedCandle] = []
    for candle in dailies:
        normalized.append(candle_to_normalized(candle))
    for candle in bundle.weekly[symbol]:
        normalized.append(candle_to_normalized(candle))
    for candle in bundle.monthly[symbol]:
        normalized.append(candle_to_normalized(candle))
    runtime.service.store_normalized(tuple(normalized), ensure_utc(evaluation_time))


def daily_candle_as_normalized(candle: Candle) -> NormalizedCandle:
    return candle_to_normalized(candle)


def eval_time_after_close(candle: Candle, delay_seconds: int = 5) -> datetime:
    return ensure_utc(candle.close_time + timedelta(seconds=delay_seconds))


def next_day_open(candle: Candle) -> datetime:
    return ensure_utc(candle.open_time + timedelta(days=1))
