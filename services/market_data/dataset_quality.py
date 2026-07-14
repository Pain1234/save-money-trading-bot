"""Dataset-scoped quality validation and reports (#81)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market_data.dataset_catalog import DatasetCatalog
from market_data.gaps import detect_gaps
from market_data.models import (
    DataQualityReport,
    DataQualityStatus,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
)
from market_data.stale import is_candle_data_stale
from market_data.validation import sort_candles, validate_candle_structure


@dataclass(frozen=True)
class DatasetQualityReportRecord:
    dataset_id: str
    report: DataQualityReport
    gap_count: int
    conflict_count: int
    stale: bool


def _evaluate_candles(
    candles: tuple[NormalizedCandle, ...],
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
) -> DataQualityReport:
    sorted_c = sort_candles(candles)
    reason_codes: list[MarketDataReasonCode] = []
    messages: list[str] = []

    for candle in sorted_c:
        problems = validate_candle_structure(candle)
        if problems:
            reason_codes.extend(problems)
            return DataQualityReport(
                status=DataQualityStatus.INVALID,
                reason_codes=tuple(dict.fromkeys(reason_codes)),
                evaluation_time=evaluation_time,
                messages=tuple(str(p) for p in problems),
            )

    gaps = detect_gaps(sorted_c, symbol, timeframe, evaluation_time)
    if gaps:
        reason_codes.append(MarketDataReasonCode.MD_GAP_DETECTED)

    last = sorted_c[-1] if sorted_c else None
    stale = is_candle_data_stale(last, evaluation_time)
    if stale:
        reason_codes.append(MarketDataReasonCode.MD_STALE)

    if gaps:
        status = DataQualityStatus.INCOMPLETE
    elif stale:
        status = DataQualityStatus.STALE
    else:
        status = DataQualityStatus.VALID
        reason_codes.append(MarketDataReasonCode.MD_VALID)

    return DataQualityReport(
        status=status,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        gaps=tuple(gaps),
        evaluation_time=evaluation_time,
        messages=tuple(messages),
    )


def evaluate_dataset_quality(
    catalog: DatasetCatalog,
    dataset_id: str,
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
) -> DatasetQualityReportRecord:
    candles = catalog.list_candles(dataset_id)
    report = _evaluate_candles(candles, symbol, timeframe, evaluation_time)
    return DatasetQualityReportRecord(
        dataset_id=dataset_id,
        report=report,
        gap_count=len(report.gaps),
        conflict_count=len(report.conflicts),
        stale=report.status == DataQualityStatus.STALE,
    )


def quality_status_from_report(report: DataQualityReport) -> DataQualityStatus:
    return report.status
