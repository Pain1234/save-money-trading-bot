"""Read-only diagnostics for daily open context deferrals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from market_data.models import (
    MarketSymbol,
    MarketTimeframe,
    StrategyDataBundle,
)
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService
from strategy_engine.constants import (
    MIN_DAILY_CANDLES,
    MIN_MONTHLY_CANDLES,
    MIN_WEEKLY_CANDLES,
)
from strategy_engine.models import StrategyParameters

from paper_trading.market_event_errors import RetryableContextNotReady


@dataclass(frozen=True)
class DailyOpenDeferSnapshot:
    """Safe, non-secret snapshot for daily open defer logging."""

    symbol: str
    error_code: str
    reason: str
    daily_count: int
    weekly_count: int
    monthly_count: int
    daily_minimum: int
    weekly_minimum: int
    monthly_minimum: int
    bundle_usable: bool
    atr14_present: bool
    market_data_ready: bool
    prior_eval_time: datetime | None = None
    evaluation_time: datetime | None = None


def _safe_reason(message: str, *, max_len: int = 160) -> str:
    cleaned = " ".join(message.replace("\r", " ").replace("\n", " ").split())
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned


def format_daily_open_defer_log(
    snapshot: DailyOpenDeferSnapshot,
    *,
    event_name: str = "daily_open_deferred",
) -> str:
    """Format a single Railway-visible log line for daily open deferrals."""
    parts = [
        event_name,
        f"symbol={snapshot.symbol}",
        f"error_code={snapshot.error_code}",
        f'reason="{_safe_reason(snapshot.reason)}"',
        f"daily_candles={snapshot.daily_count}/{snapshot.daily_minimum}",
        f"weekly_candles={snapshot.weekly_count}/{snapshot.weekly_minimum}",
        f"monthly_candles={snapshot.monthly_count}/{snapshot.monthly_minimum}",
        f"bundle_usable={'yes' if snapshot.bundle_usable else 'no'}",
        f"atr14={'yes' if snapshot.atr14_present else 'no'}",
        f"market_data_ready={'yes' if snapshot.market_data_ready else 'no'}",
    ]
    if snapshot.prior_eval_time is not None:
        parts.append(f"prior_eval_time={snapshot.prior_eval_time.isoformat()}")
    if snapshot.evaluation_time is not None:
        parts.append(f"evaluation_time={snapshot.evaluation_time.isoformat()}")
    return " ".join(parts)


def _native_closed_count(
    repository: InMemoryCandleRepository,
    symbol: str,
    timeframe: MarketTimeframe,
    evaluation_time: datetime,
) -> int:
    closed = repository.get_closed_before(
        MarketSymbol(symbol),
        timeframe,
        evaluation_time,
    )
    return len(closed)


def _atr14_present(
    bundle: StrategyDataBundle,
    prior_eval_time: datetime,
    strategy_params: StrategyParameters,
) -> bool:
    bundle_usable = bundle.is_usable
    daily_candles = bundle.daily.candles
    if not bundle_usable or not daily_candles:
        return False
    from strategy_engine.engine import StrategyEngine

    engine = StrategyEngine()
    strategy_eval = engine.evaluate(
        bundle.daily,
        bundle.weekly,
        bundle.monthly,
        prior_eval_time,
        strategy_params,
    )
    atr14 = strategy_eval.atr
    return atr14 is not None and atr14 > 0


def build_daily_open_defer_snapshot(
    *,
    symbol: str,
    error: RetryableContextNotReady,
    market_data_service: MarketDataService,
    strategy_params: StrategyParameters,
    market_data_ready: bool,
    prior_eval_time: datetime | None,
    evaluation_time: datetime,
    build_strategy_bundle: Callable[..., StrategyDataBundle],
) -> DailyOpenDeferSnapshot:
    """Collect read-only defer diagnostics without changing trading behavior."""
    if prior_eval_time is None:
        return DailyOpenDeferSnapshot(
            symbol=symbol,
            error_code=error.code,
            reason=error.message,
            daily_count=0,
            weekly_count=0,
            monthly_count=0,
            daily_minimum=MIN_DAILY_CANDLES,
            weekly_minimum=MIN_WEEKLY_CANDLES,
            monthly_minimum=MIN_MONTHLY_CANDLES,
            bundle_usable=False,
            atr14_present=False,
            market_data_ready=market_data_ready,
            prior_eval_time=None,
            evaluation_time=evaluation_time,
        )

    repository = market_data_service.repository
    daily_count = _native_closed_count(
        repository, symbol, MarketTimeframe.DAILY, prior_eval_time
    )
    weekly_count = _native_closed_count(
        repository, symbol, MarketTimeframe.WEEKLY, prior_eval_time
    )
    monthly_count = _native_closed_count(
        repository, symbol, MarketTimeframe.MONTHLY, prior_eval_time
    )

    bundle = build_strategy_bundle(
        MarketSymbol(symbol),
        prior_eval_time,
        MIN_DAILY_CANDLES,
        MIN_WEEKLY_CANDLES,
        MIN_MONTHLY_CANDLES,
        backfill=False,
        aggregate_higher_timeframes=False,
    )
    # Diagnostics must never turn a retryable lifecycle defer into a hard
    # failure when a context builder cannot provide a typed bundle.
    bundle_usable = isinstance(bundle, StrategyDataBundle) and bundle.is_usable
    atr14_present = (
        _atr14_present(bundle, prior_eval_time, strategy_params)
        if isinstance(bundle, StrategyDataBundle)
        else False
    )

    return DailyOpenDeferSnapshot(
        symbol=symbol,
        error_code=error.code,
        reason=error.message,
        daily_count=daily_count,
        weekly_count=weekly_count,
        monthly_count=monthly_count,
        daily_minimum=MIN_DAILY_CANDLES,
        weekly_minimum=MIN_WEEKLY_CANDLES,
        monthly_minimum=MIN_MONTHLY_CANDLES,
        bundle_usable=bundle_usable,
        atr14_present=atr14_present,
        market_data_ready=market_data_ready,
        prior_eval_time=prior_eval_time,
        evaluation_time=evaluation_time,
    )
