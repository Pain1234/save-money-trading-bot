"""In-memory candle repository — no database dependency."""

from __future__ import annotations

from datetime import datetime

from market_data.gaps import detect_gaps
from market_data.models import (
    CandleConflict,
    CandleGap,
    CandleKey,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
)
from market_data.timeframes import ensure_utc, is_candle_closed
from market_data.validation import candles_equal, sort_candles


class InMemoryCandleRepository:
    """Domain repository with upsert, conflict detection, and gap queries."""

    def __init__(self) -> None:
        self._store: dict[CandleKey, NormalizedCandle] = {}
        self._conflicts: list[CandleConflict] = []

    @property
    def conflicts(self) -> tuple[CandleConflict, ...]:
        return tuple(self._conflicts)

    def upsert(self, candle: NormalizedCandle) -> tuple[bool, CandleConflict | None]:
        """Insert or idempotently ignore identical duplicate."""
        candle = candle.model_copy(
            update={
                "open_time": ensure_utc(candle.open_time),
                "close_time": ensure_utc(candle.close_time),
            }
        )
        key = candle.key
        existing = self._store.get(key)
        if existing is None:
            self._store[key] = candle
            return True, None
        if candles_equal(existing, candle):
            return False, None
        conflict = CandleConflict(key=key, existing=existing, incoming=candle)
        self._conflicts.append(conflict)
        return False, conflict

    def upsert_many(
        self,
        candles: tuple[NormalizedCandle, ...],
    ) -> tuple[int, tuple[CandleConflict, ...]]:
        inserted = 0
        conflicts: list[CandleConflict] = []
        for candle in candles:
            added, conflict = self.upsert(candle)
            if added:
                inserted += 1
            if conflict is not None:
                conflicts.append(conflict)
        return inserted, tuple(conflicts)

    def get_range(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[NormalizedCandle, ...]:
        start = ensure_utc(start) if start else None
        end = ensure_utc(end) if end else None
        items = [
            c
            for k, c in self._store.items()
            if k.symbol == symbol
            and k.timeframe == timeframe
            and (start is None or c.open_time >= start)
            and (end is None or c.open_time <= end)
        ]
        return sort_candles(tuple(items))

    def get_latest(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
    ) -> NormalizedCandle | None:
        candles = self.get_range(symbol, timeframe)
        return candles[-1] if candles else None

    def get_closed_before(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        evaluation_time: datetime,
    ) -> tuple[NormalizedCandle, ...]:
        evaluation_time = ensure_utc(evaluation_time)
        candles = self.get_range(symbol, timeframe)
        return tuple(
            c for c in candles if is_candle_closed(c.close_time, evaluation_time)
        )

    def detect_gaps(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        evaluation_time: datetime,
    ) -> tuple[CandleGap, ...]:
        candles = self.get_closed_before(symbol, timeframe, evaluation_time)
        return detect_gaps(candles, symbol, timeframe, evaluation_time)

    def clear(self) -> None:
        self._store.clear()
        self._conflicts.clear()
