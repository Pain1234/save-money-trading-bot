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
from market_data.models import DataQualityStatus, MarketSymbol
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import ensure_utc

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
class StrategyBundleReadinessSnapshot:
    symbol: MarketSymbol
    daily_count: int
    weekly_count: int
    monthly_count: int
    daily_minimum: int
    weekly_minimum: int
    monthly_minimum: int
    data_quality_valid: bool
    has_conflicts: bool
    bundle_usable: bool

    @property
    def market_data_ready(self) -> bool:
        return self.bundle_usable and self.data_quality_valid and not self.has_conflicts


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
        daily_count = len(bundle.daily.candles)
        weekly_count = len(bundle.weekly.candles)
        monthly_count = len(bundle.monthly.candles)
        symbol_conflicts = tuple(
            conflict
            for conflict in repository.conflicts
            if conflict.key.symbol == symbol
        )
        snapshots.append(
            StrategyBundleReadinessSnapshot(
                symbol=symbol,
                daily_count=daily_count,
                weekly_count=weekly_count,
                monthly_count=monthly_count,
                daily_minimum=MIN_DAILY_CANDLES,
                weekly_minimum=MIN_WEEKLY_CANDLES,
                monthly_minimum=MIN_MONTHLY_CANDLES,
                data_quality_valid=bundle.report.status == DataQualityStatus.VALID,
                has_conflicts=bool(symbol_conflicts),
                bundle_usable=bundle.is_usable,
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
    return (
        f"{prefix} symbol={snapshot.symbol.value} "
        f"daily_candles={snapshot.daily_count}/{snapshot.daily_minimum} "
        f"weekly_candles={snapshot.weekly_count}/{snapshot.weekly_minimum} "
        f"monthly_candles={snapshot.monthly_count}/{snapshot.monthly_minimum} "
        f"bundle_usable={'yes' if snapshot.bundle_usable else 'no'} "
        f"market_data_ready={'yes' if snapshot.market_data_ready else 'no'}"
    )
