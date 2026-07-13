"""Initial Hyperliquid backfill window and native strategy bundle readiness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from strategy_engine.constants import (
    MIN_DAILY_CANDLES,
    MIN_MONTHLY_CANDLES,
    MIN_WEEKLY_CANDLES,
)

from market_data.bundle import get_strategy_bundle
from market_data.gaps import detect_gaps
from market_data.models import (
    DataQualityStatus,
    MarketSymbol,
    MarketTimeframe,
)
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import ensure_utc
from market_data.validation import validate_series

MINIMUM_INITIAL_BACKFILL_DAYS = 730


def compute_initial_backfill_start(evaluation_time: datetime, backfill_days: int) -> datetime:
    """Return UTC start time for an empty-repository initial backfill."""
    if backfill_days < MINIMUM_INITIAL_BACKFILL_DAYS:
        raise ValueError(
            f"initial_backfill_days must be at least {MINIMUM_INITIAL_BACKFILL_DAYS}, "
            f"got {backfill_days}"
        )
    return ensure_utc(evaluation_time) - timedelta(days=backfill_days)


@dataclass(frozen=True)
class TimeframeReadinessSnapshot:
    timeframe: MarketTimeframe
    raw_count: int
    closed_count: int
    required_count: int
    last_open_time: datetime | None
    last_close_time: datetime | None
    last_is_closed: bool | None
    latest_closed_candle_time: datetime | None
    gap_count: int
    conflict_count: int
    series_valid: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class StrategyBundleReadinessSnapshot:
    symbol: MarketSymbol
    evaluation_time: datetime
    daily: TimeframeReadinessSnapshot
    weekly: TimeframeReadinessSnapshot
    monthly: TimeframeReadinessSnapshot
    bundle_usable: bool
    unusable_reasons: tuple[str, ...]

    @property
    def daily_count(self) -> int:
        return self.daily.closed_count

    @property
    def weekly_count(self) -> int:
        return self.weekly.closed_count

    @property
    def monthly_count(self) -> int:
        return self.monthly.closed_count

    @property
    def daily_minimum(self) -> int:
        return self.daily.required_count

    @property
    def weekly_minimum(self) -> int:
        return self.weekly.required_count

    @property
    def monthly_minimum(self) -> int:
        return self.monthly.required_count

    @property
    def data_quality_valid(self) -> bool:
        return all(item.series_valid for item in (self.daily, self.weekly, self.monthly))

    @property
    def has_conflicts(self) -> bool:
        return any(item.conflict_count for item in (self.daily, self.weekly, self.monthly))

    @property
    def market_data_ready(self) -> bool:
        return self.bundle_usable and self.data_quality_valid and not self.has_conflicts


def _series_readiness(
    repository: InMemoryCandleRepository,
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
    required_count: int,
) -> TimeframeReadinessSnapshot:
    raw = repository.get_range(symbol, timeframe)
    closed = repository.get_closed_before(symbol, timeframe, evaluation_time)
    conflict_count = sum(
        1
        for conflict in repository.conflicts
        if conflict.key.symbol == symbol and conflict.key.timeframe == timeframe
    )
    gap_time = (
        evaluation_time
        if timeframe == MarketTimeframe.DAILY or not closed
        else min(evaluation_time, closed[-1].close_time)
    )
    gaps = detect_gaps(closed, symbol, timeframe, gap_time)
    conflicts = tuple(
        conflict
        for conflict in repository.conflicts
        if conflict.key.symbol == symbol and conflict.key.timeframe == timeframe
    )
    report = validate_series(
        closed,
        symbol,
        timeframe,
        evaluation_time,
        gaps=gaps,
        conflicts=conflicts,
    )
    last = raw[-1] if raw else None
    latest_closed = closed[-1] if closed else None
    return TimeframeReadinessSnapshot(
        timeframe=timeframe,
        raw_count=len(raw),
        closed_count=len(closed),
        required_count=required_count,
        last_open_time=last.open_time if last else None,
        last_close_time=last.close_time if last else None,
        last_is_closed=last.is_closed if last else None,
        latest_closed_candle_time=(latest_closed.close_time if latest_closed else None),
        gap_count=len(gaps),
        conflict_count=conflict_count,
        series_valid=report.status == DataQualityStatus.VALID,
        reason_codes=tuple(code.value for code in report.reason_codes),
    )


def _unusable_reasons(
    bundle_usable: bool,
    series: tuple[TimeframeReadinessSnapshot, ...],
    bundle_reason_codes: tuple[str, ...],
) -> tuple[str, ...]:
    if bundle_usable:
        return ()
    reasons: list[str] = []
    labels = {
        MarketTimeframe.DAILY: "daily",
        MarketTimeframe.WEEKLY: "weekly",
        MarketTimeframe.MONTHLY: "monthly",
    }
    for item in series:
        label = labels[item.timeframe]
        if item.closed_count < item.required_count:
            reasons.append(f"{label}_closed_below_minimum")
        if item.gap_count:
            reasons.append(f"{label}_gaps")
        if item.conflict_count:
            reasons.append(f"{label}_conflicts")
        if not item.series_valid:
            reasons.extend(f"{label}_{code.lower()}" for code in item.reason_codes)
    reasons.extend(f"bundle_{code.lower()}" for code in bundle_reason_codes)
    return tuple(dict.fromkeys(reasons)) or ("bundle_not_usable",)


def evaluate_native_strategy_bundle_readiness(
    repository: InMemoryCandleRepository,
    symbols: tuple[MarketSymbol, ...],
    evaluation_time: datetime,
) -> tuple[StrategyBundleReadinessSnapshot, ...]:
    """Check native bundle usability without higher-timeframe aggregation."""
    evaluation_time = ensure_utc(evaluation_time)
    snapshots: list[StrategyBundleReadinessSnapshot] = []
    for symbol in symbols:
        bundle = get_strategy_bundle(
            repository,
            symbol,
            evaluation_time,
            MIN_DAILY_CANDLES,
            MIN_WEEKLY_CANDLES,
            MIN_MONTHLY_CANDLES,
            aggregate_higher_timeframes=False,
        )
        daily = _series_readiness(
            repository,
            symbol,
            MarketTimeframe.DAILY,
            evaluation_time,
            MIN_DAILY_CANDLES,
        )
        weekly = _series_readiness(
            repository,
            symbol,
            MarketTimeframe.WEEKLY,
            evaluation_time,
            MIN_WEEKLY_CANDLES,
        )
        monthly = _series_readiness(
            repository,
            symbol,
            MarketTimeframe.MONTHLY,
            evaluation_time,
            MIN_MONTHLY_CANDLES,
        )
        bundle_reason_codes = tuple(code.value for code in bundle.report.reason_codes)
        snapshots.append(
            StrategyBundleReadinessSnapshot(
                symbol=symbol,
                evaluation_time=evaluation_time,
                daily=daily,
                weekly=weekly,
                monthly=monthly,
                bundle_usable=bundle.is_usable,
                unusable_reasons=_unusable_reasons(
                    bundle.is_usable,
                    (daily, weekly, monthly),
                    bundle_reason_codes,
                ),
            )
        )
    return tuple(snapshots)


def format_initial_backfill_log(snapshot: StrategyBundleReadinessSnapshot) -> str:
    """Railway-visible single-line startup diagnostic without secrets."""
    prefix = (
        "initial_backfill_complete"
        if snapshot.market_data_ready
        else "initial_backfill_insufficient"
    )
    fields = initial_backfill_log_fields(snapshot)
    rendered = " ".join(f"{key}={value}" for key, value in fields.items())
    return f"{prefix} {rendered}"


def initial_backfill_log_fields(
    snapshot: StrategyBundleReadinessSnapshot,
) -> dict[str, str | int]:
    """Return structured diagnostics containing counts and timestamps, never prices."""
    fields: dict[str, str | int] = {
        "symbol": snapshot.symbol.value,
        "evaluation_time": snapshot.evaluation_time.isoformat(),
    }
    for name, item in (
        ("daily", snapshot.daily),
        ("weekly", snapshot.weekly),
        ("monthly", snapshot.monthly),
    ):
        fields.update(
            {
                f"{name}_raw_count": item.raw_count,
                f"{name}_closed_count": item.closed_count,
                f"{name}_required_count": item.required_count,
                f"{name}_last_open_time": (
                    item.last_open_time.isoformat() if item.last_open_time else "none"
                ),
                f"{name}_last_close_time": (
                    item.last_close_time.isoformat() if item.last_close_time else "none"
                ),
                f"{name}_last_is_closed": (
                    "none" if item.last_is_closed is None else str(item.last_is_closed).lower()
                ),
                f"{name}_latest_closed_candle_time": (
                    item.latest_closed_candle_time.isoformat()
                    if item.latest_closed_candle_time
                    else "none"
                ),
                f"{name}_gaps": item.gap_count,
                f"{name}_conflicts": item.conflict_count,
                f"{name}_series_valid": str(item.series_valid).lower(),
                f"{name}_reason_codes": ",".join(item.reason_codes) or "none",
            }
        )
    fields.update(
        {
            "bundle_usable": "yes" if snapshot.bundle_usable else "no",
            "bundle_unusable_reasons": ",".join(snapshot.unusable_reasons) or "none",
            "market_data_ready": "yes" if snapshot.market_data_ready else "no",
        }
    )
    return fields
