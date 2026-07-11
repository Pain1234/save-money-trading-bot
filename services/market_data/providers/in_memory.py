"""In-memory provider implementations for tests."""

from __future__ import annotations

from datetime import datetime

from market_data.models import CandleGap, MarketSymbol, MarketTimeframe, RawCandle
from market_data.symbols import to_provider_symbol

ProviderSeriesMap = dict[tuple[MarketSymbol, MarketTimeframe], tuple[RawCandle, ...]]


class InMemoryHistoricalProvider:
    def __init__(self, data: ProviderSeriesMap) -> None:
        self._data = data

    def fetch_history(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start: datetime,
        end: datetime,
        *,
        limit: int = 500,
    ) -> tuple[RawCandle, ...]:
        candles = self._data.get((symbol, timeframe), ())
        filtered = tuple(c for c in candles if start <= c.open_time <= end)
        return filtered[:limit]


class InMemoryLiveProvider:
    def __init__(self) -> None:
        self._connected = False
        self._subscribed: tuple[MarketSymbol, ...] = ()
        self._queue: list[RawCandle] = []

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe(self, symbols: tuple[MarketSymbol, ...]) -> None:
        self._subscribed = symbols

    def push(self, candle: RawCandle) -> None:
        self._queue.append(candle)

    def poll_events(self) -> tuple[RawCandle, ...]:
        if not self._connected:
            return ()
        events = tuple(self._queue)
        self._queue.clear()
        return events


class InMemoryBackfillProvider:
    def __init__(self, data: ProviderSeriesMap) -> None:
        self._data = data
        self.fail = False

    def backfill_gaps(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        gaps: tuple[CandleGap, ...],
        *,
        limit: int = 500,
    ) -> tuple[RawCandle, ...]:
        if self.fail:
            return ()
        missing_times = {
            g.missing_open_time
            for g in gaps
            if g.symbol == symbol and g.timeframe == timeframe
        }
        available = self._data.get((symbol, timeframe), ())
        return tuple(
            c for c in available if c.open_time in missing_times
        )[:limit]


def raw_from_normalized(normalized: object) -> RawCandle:
    from market_data.models import NormalizedCandle

    assert isinstance(normalized, NormalizedCandle)
    return RawCandle(
        provider_symbol=to_provider_symbol(normalized.symbol),
        timeframe=normalized.timeframe,
        open_time=normalized.open_time,
        close_time=normalized.close_time,
        open=normalized.open,
        high=normalized.high,
        low=normalized.low,
        close=normalized.close,
        volume=normalized.volume,
        is_closed=normalized.is_closed,
    )
