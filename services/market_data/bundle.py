"""Strategy bundle assembly."""

from __future__ import annotations

from datetime import datetime

from strategy_engine.models import CandleSeries, Timeframe

from market_data.aggregation import aggregate_monthly_from_daily, aggregate_weekly_from_daily
from market_data.closed import filter_closed_candles
from market_data.gaps import detect_gaps
from market_data.merge_policy import merge_native_and_aggregated
from market_data.models import (
    CandleConflict,
    CandleGap,
    DataQualityReport,
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    StrategyDataBundle,
)
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import ensure_utc
from market_data.validation import validate_series


def _merge_reports(reports: tuple[DataQualityReport, ...]) -> DataQualityReport:
    if not reports:
        raise ValueError("No reports to merge")
    evaluation_time = reports[0].evaluation_time
    status_priority = {
        DataQualityStatus.INVALID: 4,
        DataQualityStatus.INCOMPLETE: 3,
        DataQualityStatus.STALE: 2,
        DataQualityStatus.DISCONNECTED: 2,
        DataQualityStatus.VALID: 0,
    }
    worst = max(reports, key=lambda r: status_priority.get(r.status, 0))
    codes: list[MarketDataReasonCode] = []
    gaps: list[CandleGap] = []
    conflicts: list[CandleConflict] = []
    messages: list[str] = []
    for report in reports:
        codes.extend(report.reason_codes)
        gaps.extend(report.gaps)
        conflicts.extend(report.conflicts)
        messages.extend(report.messages)
    unique_codes = tuple(dict.fromkeys(codes))
    if worst.status == DataQualityStatus.VALID:
        unique_codes = (MarketDataReasonCode.MD_VALID,)
    return DataQualityReport(
        status=worst.status,
        reason_codes=unique_codes,
        gaps=tuple(gaps),
        conflicts=tuple(conflicts),
        missing_ranges=tuple(r for rep in reports for r in rep.missing_ranges),
        last_known_candle=reports[-1].last_known_candle,
        expected_next_open=reports[-1].expected_next_open,
        evaluation_time=evaluation_time,
        messages=tuple(messages),
    )


def _conflicts_for(
    conflicts: tuple[CandleConflict, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
) -> tuple[CandleConflict, ...]:
    return tuple(
        c for c in conflicts if c.key.symbol == symbol and c.key.timeframe == timeframe
    )


def _gap_check_time(
    closed: tuple[NormalizedCandle, ...],
    evaluation_time: datetime,
    timeframe: MarketTimeframe,
) -> datetime:
    """
    Gap detection horizon for strategy bundles.

    Daily series must cover through ``evaluation_time``. Higher timeframes only
    require internal continuity of stored native history — trailing calendar
    periods after the last closed candle are not treated as gaps.
    """
    if timeframe == MarketTimeframe.DAILY or not closed:
        return evaluation_time
    return min(evaluation_time, closed[-1].close_time)


def _resolve_higher_timeframe(
    repository: InMemoryCandleRepository,
    daily_closed: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
    *,
    aggregate_higher_timeframes: bool,
) -> tuple[tuple[NormalizedCandle, ...], tuple[CandleConflict, ...]]:
    native = repository.get_closed_before(symbol, timeframe, evaluation_time)
    if not aggregate_higher_timeframes:
        return native, ()

    if timeframe == MarketTimeframe.WEEKLY:
        aggregated = aggregate_weekly_from_daily(daily_closed, symbol, evaluation_time)
    elif timeframe == MarketTimeframe.MONTHLY:
        aggregated = aggregate_monthly_from_daily(daily_closed, symbol, evaluation_time)
    else:
        return native, ()

    merged, merge_conflicts = merge_native_and_aggregated(
        native, aggregated, symbol, timeframe
    )
    return merged, merge_conflicts


def _to_series(
    candles: tuple[NormalizedCandle, ...],
    symbol: str,
    timeframe: Timeframe,
    minimum: int,
) -> CandleSeries:
    selected = candles[-minimum:] if minimum else candles
    return CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        # ``candles`` has already been filtered by close_time at evaluation_time.
        # Normalize the transport-time flag at this boundary so the Strategy
        # Engine sees the same closed semantics as Market Data without admitting
        # the current open candle.
        candles=tuple(
            c.to_strategy_candle().model_copy(update={"is_closed": True})
            for c in selected
        ),
    )


def get_strategy_bundle(
    repository: InMemoryCandleRepository,
    symbol: MarketSymbol,
    evaluation_time: datetime,
    daily_minimum: int,
    weekly_minimum: int,
    monthly_minimum: int,
    *,
    aggregate_higher_timeframes: bool = True,
) -> StrategyDataBundle:
    """Build closed, look-ahead-safe candle bundle for Strategy Engine."""
    evaluation_time = ensure_utc(evaluation_time)
    repo_conflicts = repository.conflicts

    daily_closed = repository.get_closed_before(symbol, MarketTimeframe.DAILY, evaluation_time)
    daily_gaps = detect_gaps(daily_closed, symbol, MarketTimeframe.DAILY, evaluation_time)
    daily_report = validate_series(
        daily_closed,
        symbol,
        MarketTimeframe.DAILY,
        evaluation_time,
        gaps=daily_gaps,
        conflicts=_conflicts_for(repo_conflicts, symbol, MarketTimeframe.DAILY),
    )

    weekly_all, weekly_merge_conflicts = _resolve_higher_timeframe(
        repository,
        daily_closed,
        symbol,
        MarketTimeframe.WEEKLY,
        evaluation_time,
        aggregate_higher_timeframes=aggregate_higher_timeframes,
    )
    monthly_all, monthly_merge_conflicts = _resolve_higher_timeframe(
        repository,
        daily_closed,
        symbol,
        MarketTimeframe.MONTHLY,
        evaluation_time,
        aggregate_higher_timeframes=aggregate_higher_timeframes,
    )

    weekly_closed = filter_closed_candles(weekly_all, evaluation_time)
    monthly_closed = filter_closed_candles(monthly_all, evaluation_time)

    weekly_conflicts = (
        _conflicts_for(repo_conflicts, symbol, MarketTimeframe.WEEKLY) + weekly_merge_conflicts
    )
    monthly_conflicts = (
        _conflicts_for(repo_conflicts, symbol, MarketTimeframe.MONTHLY) + monthly_merge_conflicts
    )

    weekly_gap_time = _gap_check_time(
        weekly_closed, evaluation_time, MarketTimeframe.WEEKLY
    )
    monthly_gap_time = _gap_check_time(
        monthly_closed, evaluation_time, MarketTimeframe.MONTHLY
    )

    weekly_report = validate_series(
        weekly_closed,
        symbol,
        MarketTimeframe.WEEKLY,
        evaluation_time,
        gaps=detect_gaps(weekly_closed, symbol, MarketTimeframe.WEEKLY, weekly_gap_time),
        conflicts=weekly_conflicts,
    )
    monthly_report = validate_series(
        monthly_closed,
        symbol,
        MarketTimeframe.MONTHLY,
        evaluation_time,
        gaps=detect_gaps(monthly_closed, symbol, MarketTimeframe.MONTHLY, monthly_gap_time),
        conflicts=monthly_conflicts,
    )

    merged = _merge_reports((daily_report, weekly_report, monthly_report))

    if (
        len(daily_closed) < daily_minimum
        or len(weekly_closed) < weekly_minimum
        or len(monthly_closed) < monthly_minimum
    ):
        insufficient_status = (
            DataQualityStatus.INVALID
            if merged.status == DataQualityStatus.INVALID
            else DataQualityStatus.INCOMPLETE
        )
        merged = DataQualityReport(
            status=insufficient_status,
            reason_codes=tuple(
                dict.fromkeys((*merged.reason_codes, MarketDataReasonCode.MD_INCOMPLETE))
            ),
            gaps=merged.gaps,
            conflicts=merged.conflicts,
            missing_ranges=merged.missing_ranges,
            last_known_candle=merged.last_known_candle,
            expected_next_open=merged.expected_next_open,
            evaluation_time=evaluation_time,
            messages=merged.messages + ("Insufficient candle history",),
        )

    sym = symbol.value
    return StrategyDataBundle(
        symbol=symbol,
        evaluation_time=evaluation_time,
        daily=_to_series(daily_closed, sym, Timeframe.DAILY, daily_minimum),
        weekly=_to_series(weekly_closed, sym, Timeframe.WEEKLY, weekly_minimum),
        monthly=_to_series(monthly_closed, sym, Timeframe.MONTHLY, monthly_minimum),
        report=merged,
    )
