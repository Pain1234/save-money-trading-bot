"""Provider protocol definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from market_data.models import (
    CandleGap,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    RawCandle,
)


class HistoricalCandleProvider(Protocol):
    def fetch_history(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start: datetime,
        end: datetime,
        *,
        limit: int = 500,
    ) -> tuple[RawCandle, ...]: ...


class LiveCandleProvider(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def subscribe(self, symbols: tuple[MarketSymbol, ...]) -> None: ...

    def poll_events(self) -> tuple[RawCandle, ...]: ...


class BackfillProvider(Protocol):
    def backfill_gaps(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        gaps: tuple[CandleGap, ...],
        *,
        limit: int = 500,
    ) -> tuple[RawCandle, ...]: ...


class CandleRepository(Protocol):
    def upsert(self, candle: object) -> tuple[bool, object | None]: ...

    def get_range(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[NormalizedCandle, ...]: ...

    def get_latest(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
    ) -> object | None: ...

    def get_closed_before(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        evaluation_time: datetime,
    ) -> tuple[NormalizedCandle, ...]: ...

    def detect_gaps(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        evaluation_time: datetime,
    ) -> tuple[CandleGap, ...]: ...
