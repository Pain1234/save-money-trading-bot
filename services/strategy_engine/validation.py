"""Candle series validation — fail-closed."""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from strategy_engine.models import (
    Candle,
    CandleSeries,
    DataQualityStatus,
    ReasonCode,
    StrategyError,
    StrategyParameters,
    Timeframe,
)


def _is_finite_decimal(value: Decimal) -> bool:
    try:
        f = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(f)


def _validate_ohlc(candle: Candle) -> StrategyError | None:
    o, h, low, c = candle.open, candle.high, candle.low, candle.close
    fields = (
        ("open", o),
        ("high", h),
        ("low", low),
        ("close", c),
        ("volume", candle.volume),
    )
    for name, val in fields:
        if not _is_finite_decimal(val):
            return StrategyError(
                code=ReasonCode.RC_REJECT_DATA,
                message=f"{name} is NaN or Infinity",
                details={"open_time": candle.open_time.isoformat()},
            )
    if o <= 0 or h <= 0 or low <= 0 or c <= 0:
        return StrategyError(
            code=ReasonCode.RC_REJECT_DATA,
            message="OHLC values must be greater than zero",
            details={"open_time": candle.open_time.isoformat()},
        )
    if h < o or h < c or h < low:
        return StrategyError(
            code=ReasonCode.RC_REJECT_DATA,
            message="high must be >= open, close, and low",
            details={"open_time": candle.open_time.isoformat()},
        )
    if low > o or low > c or low > h:
        return StrategyError(
            code=ReasonCode.RC_REJECT_DATA,
            message="low must be <= open, close, and high",
            details={"open_time": candle.open_time.isoformat()},
        )
    if candle.volume < 0:
        return StrategyError(
            code=ReasonCode.RC_REJECT_DATA,
            message="volume must be >= 0",
            details={"open_time": candle.open_time.isoformat()},
        )
    return None


def validate_candle_series(
    series: CandleSeries,
    evaluation_time: datetime,
    *,
    expected_timeframe: Timeframe | None = None,
) -> tuple[DataQualityStatus, tuple[StrategyError, ...]]:
    """
    Validate candle series for strategy evaluation.

    Returns (data_quality_status, errors). Fail-closed on any error.
    """
    errors: list[StrategyError] = []

    if expected_timeframe is not None and series.timeframe != expected_timeframe:
        errors.append(
            StrategyError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Incorrect timeframe",
                details={
                    "expected": expected_timeframe.value,
                    "actual": series.timeframe.value,
                },
            )
        )

    candles = series.candles
    if not candles:
        errors.append(
            StrategyError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Empty candle series",
            )
        )
        return DataQualityStatus.INVALID_DATA, tuple(errors)

    seen_times: set[datetime] = set()
    prev_open_time: datetime | None = None

    for candle in candles:
        if candle.symbol != series.symbol:
            errors.append(
                StrategyError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Symbol mismatch in candle series",
                    details={"expected": series.symbol, "actual": candle.symbol},
                )
            )

        if candle.timeframe != series.timeframe:
            errors.append(
                StrategyError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Timeframe mismatch in candle",
                    details={"open_time": candle.open_time.isoformat()},
                )
            )

        if not candle.is_closed:
            errors.append(
                StrategyError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Open (unclosed) candle not allowed",
                    details={"open_time": candle.open_time.isoformat()},
                )
            )

        if evaluation_time < candle.close_time:
            errors.append(
                StrategyError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Evaluation time before candle close_time",
                    details={
                        "open_time": candle.open_time.isoformat(),
                        "close_time": candle.close_time.isoformat(),
                        "evaluation_time": evaluation_time.isoformat(),
                    },
                )
            )

        if candle.open_time in seen_times:
            errors.append(
                StrategyError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Duplicate candle timestamp",
                    details={"open_time": candle.open_time.isoformat()},
                )
            )
        seen_times.add(candle.open_time)

        if prev_open_time is not None and candle.open_time <= prev_open_time:
            errors.append(
                StrategyError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Candles not strictly chronologically sorted by open_time",
                    details={"open_time": candle.open_time.isoformat()},
                )
            )
        prev_open_time = candle.open_time

        ohlc_err = _validate_ohlc(candle)
        if ohlc_err is not None:
            errors.append(ohlc_err)

    if errors:
        return DataQualityStatus.INVALID_DATA, tuple(errors)

    min_required = min_candles_for_warmup(series.timeframe)
    if len(candles) < min_required:
        errors.append(
            StrategyError(
                code=ReasonCode.RC_REJECT_WARMUP,
                message="Insufficient history for timeframe",
                details={
                    "timeframe": series.timeframe.value,
                    "required": min_required,
                    "actual": len(candles),
                },
            )
        )
        return DataQualityStatus.INSUFFICIENT_HISTORY, tuple(errors)

    return DataQualityStatus.OK, tuple()


def min_candles_for_warmup(
    timeframe: Timeframe,
    params: StrategyParameters | None = None,
) -> int:
    """Minimum closed candles derived from configured indicator periods."""
    p = params or StrategyParameters()
    if timeframe == Timeframe.DAILY:
        return max(
            p.daily_ema_period,
            p.atr_period + 1,
            p.volume_sma_period,
            p.breakout_lookback + 1,
        )
    if timeframe == Timeframe.WEEKLY:
        return max(p.weekly_ema_slow, p.weekly_ema_fast + 1)
    if timeframe == Timeframe.MONTHLY:
        return p.monthly_ema_period
    raise ValueError(f"Unknown timeframe: {timeframe}")


def _min_candles_for_timeframe(timeframe: Timeframe) -> int:
    return min_candles_for_warmup(timeframe)


def check_warmup_complete(
    daily_count: int,
    weekly_count: int,
    monthly_count: int,
    params: StrategyParameters | None = None,
) -> bool:
    """Strategy Spec §3.1 WARMUP_complete using configured periods."""
    p = params or StrategyParameters()
    return (
        daily_count >= min_candles_for_warmup(Timeframe.DAILY, p)
        and weekly_count >= min_candles_for_warmup(Timeframe.WEEKLY, p)
        and monthly_count >= min_candles_for_warmup(Timeframe.MONTHLY, p)
    )
