"""Market Data Service orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from market_data.bundle import get_strategy_bundle
from market_data.gaps import detect_gaps
from market_data.ingest import IngestResult, ingest_normalized
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
    StrategyDataBundle,
)
from market_data.normalize import normalize_batch
from market_data.providers.protocols import BackfillProvider, HistoricalCandleProvider
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import ensure_utc
from market_data.validation import validate_raw_candle, validate_series


def _report_from_ingest(
    result: IngestResult,
    evaluation_time: datetime,
    *,
    symbol: MarketSymbol | None = None,
    timeframe: MarketTimeframe | None = None,
) -> DataQualityReport:
    status = DataQualityStatus.INVALID if result.rejected else DataQualityStatus.VALID
    if result.conflicts:
        status = DataQualityStatus.INVALID
    return DataQualityReport(
        status=status,
        reason_codes=result.reason_codes or (MarketDataReasonCode.MD_INVALID,),
        conflicts=result.conflicts,
        evaluation_time=evaluation_time,
    )


def _merge_backfill_reason_codes(
    report: DataQualityReport,
    *,
    gaps: tuple[CandleGap, ...],
) -> DataQualityReport:
    codes = list(report.reason_codes)
    if gaps and MarketDataReasonCode.MD_GAP_DETECTED not in codes:
        codes.insert(0, MarketDataReasonCode.MD_GAP_DETECTED)
    if MarketDataReasonCode.MD_BACKFILL_FAILED not in codes:
        codes.append(MarketDataReasonCode.MD_BACKFILL_FAILED)
    return report.model_copy(
        update={
            "status": DataQualityStatus.INCOMPLETE,
            "reason_codes": tuple(dict.fromkeys(codes)),
        }
    )


class MarketDataService:
    """Read-only market data orchestrator."""

    def __init__(
        self,
        repository: InMemoryCandleRepository,
        *,
        historical: HistoricalCandleProvider | None = None,
        backfill: BackfillProvider | None = None,
    ) -> None:
        self._repository = repository
        self._historical = historical
        self._backfill = backfill

    @property
    def repository(self) -> InMemoryCandleRepository:
        return self._repository

    def ingest_raw(
        self,
        raws: tuple[RawCandle, ...],
        evaluation_time: datetime,
        *,
        expected_symbol: MarketSymbol | None = None,
    ) -> tuple[int, DataQualityReport | None]:
        evaluation_time = ensure_utc(evaluation_time)
        rejected_codes: list[MarketDataReasonCode] = []
        valid_raws: list[RawCandle] = []
        for raw in raws:
            codes = validate_raw_candle(raw)
            if codes:
                rejected_codes.extend(codes)
            else:
                valid_raws.append(raw)
        if rejected_codes and not valid_raws:
            return 0, DataQualityReport(
                status=DataQualityStatus.INVALID,
                reason_codes=tuple(dict.fromkeys(rejected_codes)),
                evaluation_time=evaluation_time,
            )
        normalized = normalize_batch(
            tuple(valid_raws), evaluation_time, expected_symbol=expected_symbol
        )
        result = ingest_normalized(self._repository, normalized, evaluation_time)
        all_codes = tuple(dict.fromkeys((*rejected_codes, *result.reason_codes)))
        if rejected_codes:
            return result.inserted, DataQualityReport(
                status=DataQualityStatus.INVALID,
                reason_codes=all_codes,
                conflicts=result.conflicts,
                evaluation_time=evaluation_time,
            )
        if result.rejected or result.conflicts:
            sample = normalized[0] if normalized else None
            sym = expected_symbol or (sample.symbol if sample else MarketSymbol.BTC)
            tf = sample.timeframe if sample else MarketTimeframe.DAILY
            report = _report_from_ingest(result, evaluation_time)
            if result.conflicts:
                return result.inserted, validate_series(
                    self._repository.get_closed_before(sym, tf, evaluation_time),
                    sym,
                    tf,
                    evaluation_time,
                    conflicts=result.conflicts,
                )
            return result.inserted, report
        return result.inserted, None

    def load_history(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start: datetime,
        end: datetime,
        evaluation_time: datetime,
        *,
        limit: int = 500,
    ) -> tuple[int, DataQualityReport | None]:
        if self._historical is None:
            raise RuntimeError("Historical provider not configured")
        raws = self._historical.fetch_history(symbol, timeframe, start, end, limit=limit)
        return self.ingest_raw(raws, evaluation_time, expected_symbol=symbol)

    def attempt_backfill(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        evaluation_time: datetime,
        *,
        limit: int = 500,
    ) -> DataQualityReport:
        evaluation_time = ensure_utc(evaluation_time)
        if self._backfill is None:
            candles = self._repository.get_closed_before(symbol, timeframe, evaluation_time)
            gaps = detect_gaps(candles, symbol, timeframe, evaluation_time)
            report = validate_series(
                candles,
                symbol,
                timeframe,
                evaluation_time,
                gaps=gaps,
            )
            return _merge_backfill_reason_codes(report, gaps=gaps)

        candles = self._repository.get_closed_before(symbol, timeframe, evaluation_time)
        gaps = detect_gaps(candles, symbol, timeframe, evaluation_time)
        if not gaps:
            return validate_series(candles, symbol, timeframe, evaluation_time)

        raws = self._backfill.backfill_gaps(symbol, timeframe, gaps, limit=limit)
        if not raws:
            report = validate_series(
                candles,
                symbol,
                timeframe,
                evaluation_time,
                gaps=gaps,
            )
            return _merge_backfill_reason_codes(report, gaps=gaps)

        self.ingest_raw(raws, evaluation_time, expected_symbol=symbol)
        refreshed = self._repository.get_closed_before(symbol, timeframe, evaluation_time)
        remaining_gaps = detect_gaps(refreshed, symbol, timeframe, evaluation_time)
        report = validate_series(
            refreshed,
            symbol,
            timeframe,
            evaluation_time,
            gaps=remaining_gaps,
            conflicts=_conflicts_for_repo(symbol, timeframe, self._repository.conflicts),
        )
        if remaining_gaps:
            return _merge_backfill_reason_codes(report, gaps=remaining_gaps)
        return report

    def build_strategy_bundle(
        self,
        symbol: MarketSymbol,
        evaluation_time: datetime,
        daily_minimum: int,
        weekly_minimum: int,
        monthly_minimum: int,
        *,
        backfill: bool = True,
        aggregate_higher_timeframes: bool = True,
    ) -> StrategyDataBundle:
        evaluation_time = ensure_utc(evaluation_time)
        if backfill:
            for tf in (MarketTimeframe.DAILY, MarketTimeframe.WEEKLY, MarketTimeframe.MONTHLY):
                self.attempt_backfill(symbol, tf, evaluation_time)
        return get_strategy_bundle(
            self._repository,
            symbol,
            evaluation_time,
            daily_minimum,
            weekly_minimum,
            monthly_minimum,
            aggregate_higher_timeframes=aggregate_higher_timeframes,
        )

    def store_normalized(
        self,
        candles: tuple[NormalizedCandle, ...],
        evaluation_time: datetime | None = None,
    ) -> IngestResult:
        if not candles:
            eval_time = ensure_utc(datetime.now(tz=UTC))
        elif evaluation_time is not None:
            eval_time = ensure_utc(evaluation_time)
        else:
            eval_time = ensure_utc(max(c.close_time for c in candles))
        return ingest_normalized(self._repository, candles, eval_time)


def _conflicts_for_repo(
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    conflicts: tuple[CandleConflict, ...],
) -> tuple[CandleConflict, ...]:
    return tuple(
        c for c in conflicts if c.key.symbol == symbol and c.key.timeframe == timeframe
    )
