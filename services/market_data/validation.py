"""Candle validation — fail-closed, no silent corrections."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from market_data.models import (
    CandleConflict,
    CandleGap,
    DataQualityReport,
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    RawCandle,
)
from market_data.timeframes import ensure_utc, is_candle_closed, is_valid_timeframe_duration


def _is_finite_decimal(value: Decimal) -> bool:
    return value.is_finite()


def validate_raw_candle(raw: RawCandle) -> tuple[MarketDataReasonCode, ...]:
    """Validate provider payload before normalization."""
    codes: list[MarketDataReasonCode] = []
    for val in (raw.open, raw.high, raw.low, raw.close):
        if not _is_finite_decimal(val):
            codes.append(MarketDataReasonCode.MD_INVALID_OHLC)
            return tuple(dict.fromkeys(codes))

    if not _is_finite_decimal(raw.volume):
        codes.append(MarketDataReasonCode.MD_INVALID_VOLUME)
        return tuple(dict.fromkeys(codes))

    if raw.volume < 0:
        codes.append(MarketDataReasonCode.MD_INVALID_VOLUME)

    return tuple(dict.fromkeys(codes))


def validate_candle_structure(candle: NormalizedCandle) -> tuple[MarketDataReasonCode, ...]:
    """Structural validation for persist — no evaluation-time temporal gate."""
    codes: list[MarketDataReasonCode] = []

    if candle.symbol.value not in {s.value for s in MarketSymbol}:
        codes.append(MarketDataReasonCode.MD_UNKNOWN_SYMBOL)

    o, h, low, c = candle.open, candle.high, candle.low, candle.close
    for val in (o, h, low, c):
        if not _is_finite_decimal(val):
            codes.append(MarketDataReasonCode.MD_INVALID_OHLC)
            return tuple(dict.fromkeys(codes))

    if not _is_finite_decimal(candle.volume):
        codes.append(MarketDataReasonCode.MD_INVALID_VOLUME)
        return tuple(dict.fromkeys(codes))

    if o <= 0 or h <= 0 or low <= 0 or c <= 0:
        codes.append(MarketDataReasonCode.MD_INVALID_OHLC)

    if candle.volume < 0:
        codes.append(MarketDataReasonCode.MD_INVALID_VOLUME)

    if h < o or h < c or h < low:
        codes.append(MarketDataReasonCode.MD_INVALID_OHLC)
    if low > o or low > c or low > h:
        codes.append(MarketDataReasonCode.MD_INVALID_OHLC)

    if candle.open_time >= candle.close_time:
        codes.append(MarketDataReasonCode.MD_INVALID_TIMEFRAME)

    if not is_valid_timeframe_duration(candle.open_time, candle.close_time, candle.timeframe):
        codes.append(MarketDataReasonCode.MD_INVALID_TIMEFRAME)

    return tuple(dict.fromkeys(codes))


def validate_single_candle(
    candle: NormalizedCandle,
    evaluation_time: datetime,
) -> tuple[MarketDataReasonCode, ...]:
    """Validate one candle; return reason codes (empty if valid)."""
    codes = list(validate_candle_structure(candle))
    evaluation_time = ensure_utc(evaluation_time)

    if not is_candle_closed(candle.close_time, evaluation_time):
        if candle.close_time > evaluation_time:
            codes.append(MarketDataReasonCode.MD_FUTURE_CANDLE)
        else:
            codes.append(MarketDataReasonCode.MD_OPEN_CANDLE_EXCLUDED)

    return tuple(dict.fromkeys(codes))


def candles_equal(a: NormalizedCandle, b: NormalizedCandle) -> bool:
    return (
        a.symbol == b.symbol
        and a.timeframe == b.timeframe
        and a.open_time == b.open_time
        and a.close_time == b.close_time
        and a.open == b.open
        and a.high == b.high
        and a.low == b.low
        and a.close == b.close
        and a.volume == b.volume
        and a.is_closed == b.is_closed
    )


def sort_candles(candles: tuple[NormalizedCandle, ...]) -> tuple[NormalizedCandle, ...]:
    return tuple(sorted(candles, key=lambda c: c.open_time))


def detect_conflicts(
    candles: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
) -> tuple[CandleConflict, ...]:
    """Find duplicate candle keys with differing OHLCV."""
    from market_data.models import CandleKey

    conflicts: list[CandleConflict] = []
    by_key: dict[CandleKey, NormalizedCandle] = {}
    for candle in sort_candles(candles):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            continue
        key = CandleKey(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            open_time=candle.open_time,
        )
        existing = by_key.get(key)
        if existing is not None and not candles_equal(existing, candle):
            conflicts.append(
                CandleConflict(key=key, existing=existing, incoming=candle)
            )
        else:
            by_key[key] = candle
    return tuple(conflicts)


def validate_series(
    candles: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
    *,
    gaps: tuple[CandleGap, ...] = (),
    conflicts: tuple[CandleConflict, ...] = (),
) -> DataQualityReport:
    """Validate an ordered candle series at ``evaluation_time``."""
    evaluation_time = ensure_utc(evaluation_time)
    reason_codes: list[MarketDataReasonCode] = []
    messages: list[str] = []

    if not candles:
        return DataQualityReport(
            status=DataQualityStatus.INCOMPLETE,
            reason_codes=(MarketDataReasonCode.MD_INCOMPLETE,),
            evaluation_time=evaluation_time,
            messages=("No candles available",),
        )

    sorted_candles = sort_candles(candles)
    if list(sorted_candles) != list(candles):
        reason_codes.append(MarketDataReasonCode.MD_INVALID)
        messages.append("Candles are not chronologically sorted")

    seen_opens: set[datetime] = set()
    last_open: datetime | None = None
    last_candle: NormalizedCandle | None = None

    for candle in sorted_candles:
        if candle.symbol != symbol or candle.timeframe != timeframe:
            reason_codes.append(MarketDataReasonCode.MD_INVALID)
            messages.append(
                f"Symbol/timeframe mismatch at {candle.open_time.isoformat()}"
            )

        single_codes = validate_single_candle(candle, evaluation_time)
        reason_codes.extend(single_codes)

        if candle.open_time in seen_opens:
            reason_codes.append(MarketDataReasonCode.MD_DUPLICATE_CONFLICT)
        seen_opens.add(candle.open_time)

        if last_candle is not None and candle.open_time <= last_candle.close_time:
            reason_codes.append(MarketDataReasonCode.MD_INVALID)
            messages.append(
                f"Overlapping interval at {candle.open_time.isoformat()}"
            )

        if last_open is not None and candle.open_time <= last_open:
            reason_codes.append(MarketDataReasonCode.MD_INVALID)
            messages.append(f"Overlap or unsorted open at {candle.open_time.isoformat()}")

        last_open = candle.open_time
        last_candle = candle

    if gaps:
        reason_codes.append(MarketDataReasonCode.MD_GAP_DETECTED)
    if conflicts:
        reason_codes.append(MarketDataReasonCode.MD_DUPLICATE_CONFLICT)

    unique_codes = tuple(dict.fromkeys(reason_codes))
    missing_ranges = tuple(
        (g.missing_open_time, g.expected_close_time) for g in gaps
    )

    if any(
        c
        in (
            MarketDataReasonCode.MD_INVALID_OHLC,
            MarketDataReasonCode.MD_INVALID_VOLUME,
            MarketDataReasonCode.MD_INVALID_TIMEFRAME,
            MarketDataReasonCode.MD_DUPLICATE_CONFLICT,
            MarketDataReasonCode.MD_UNKNOWN_SYMBOL,
        )
        for c in unique_codes
    ):
        status = DataQualityStatus.INVALID
    elif MarketDataReasonCode.MD_GAP_DETECTED in unique_codes:
        status = DataQualityStatus.INCOMPLETE
    elif any(
        c in (MarketDataReasonCode.MD_FUTURE_CANDLE, MarketDataReasonCode.MD_OPEN_CANDLE_EXCLUDED)
        for c in unique_codes
    ):
        status = DataQualityStatus.INVALID
    elif unique_codes:
        status = DataQualityStatus.INVALID
    else:
        status = DataQualityStatus.VALID
        unique_codes = (MarketDataReasonCode.MD_VALID,)

    expected_next = None
    if last_candle is not None:
        from market_data.timeframes import next_open_time

        expected_next = next_open_time(last_candle.open_time, timeframe)

    return DataQualityReport(
        status=status,
        reason_codes=unique_codes,
        gaps=gaps,
        conflicts=conflicts,
        missing_ranges=missing_ranges,
        last_known_candle=last_candle,
        expected_next_open=expected_next,
        evaluation_time=evaluation_time,
        messages=tuple(messages),
    )
