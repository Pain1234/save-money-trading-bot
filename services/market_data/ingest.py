"""Shared ingest path — validate before persist."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market_data.models import CandleConflict, MarketDataReasonCode, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import ensure_utc
from market_data.validation import validate_candle_structure


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    identical_skipped: int
    rejected: tuple[tuple[MarketDataReasonCode, ...], ...]
    conflicts: tuple[CandleConflict, ...]
    reason_codes: tuple[MarketDataReasonCode, ...]


def ingest_normalized(
    repository: InMemoryCandleRepository,
    candles: tuple[NormalizedCandle, ...],
    evaluation_time: datetime,
) -> IngestResult:
    """Validate structure and upsert; never persist invalid candles."""
    _ = ensure_utc(evaluation_time)
    inserted = 0
    identical_skipped = 0
    rejected: list[tuple[MarketDataReasonCode, ...]] = []
    conflicts: list[CandleConflict] = []
    emitted: list[MarketDataReasonCode] = []

    for candle in candles:
        normalized = candle.model_copy(
            update={
                "open_time": ensure_utc(candle.open_time),
                "close_time": ensure_utc(candle.close_time),
            }
        )
        codes = validate_candle_structure(normalized)
        if codes:
            rejected.append(codes)
            emitted.extend(codes)
            continue

        added, conflict = repository.upsert(normalized)
        if conflict is not None:
            conflicts.append(conflict)
            emitted.append(MarketDataReasonCode.MD_DUPLICATE_CONFLICT)
        elif added:
            inserted += 1
        else:
            identical_skipped += 1
            emitted.append(MarketDataReasonCode.MD_DUPLICATE_IDENTICAL)

    unique_codes = tuple(dict.fromkeys(emitted))
    return IngestResult(
        inserted=inserted,
        identical_skipped=identical_skipped,
        rejected=tuple(rejected),
        conflicts=tuple(conflicts),
        reason_codes=unique_codes,
    )
