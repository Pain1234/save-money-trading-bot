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
from strategy_engine.indicators import compute_true_range
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
    input_candle_count: int = 0
    first_input_open_time: datetime | None = None
    last_input_open_time: datetime | None = None
    last_input_is_closed: bool | None = None
    true_range_count: int = 0
    valid_true_range_count: int = 0
    atr_window: int = 14
    indicator_reason_code: str = "NOT_EVALUATED"


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
        f"input_candle_count={snapshot.input_candle_count}",
        f"first_input_open_time={_format_time(snapshot.first_input_open_time)}",
        f"last_input_open_time={_format_time(snapshot.last_input_open_time)}",
        f"last_input_is_closed={_format_bool(snapshot.last_input_is_closed)}",
        f"true_range_count={snapshot.true_range_count}",
        f"valid_true_range_count={snapshot.valid_true_range_count}",
        f"atr_window={snapshot.atr_window}",
        f"indicator_reason_code={snapshot.indicator_reason_code}",
    ]
    if snapshot.prior_eval_time is not None:
        parts.append(f"prior_eval_time={snapshot.prior_eval_time.isoformat()}")
    if snapshot.evaluation_time is not None:
        parts.append(f"evaluation_time={snapshot.evaluation_time.isoformat()}")
    return " ".join(parts)


def _format_time(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "none"


def _format_bool(value: bool | None) -> str:
    return "none" if value is None else ("yes" if value else "no")


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


@dataclass(frozen=True)
class _AtrDiagnostic:
    present: bool
    input_candle_count: int
    first_input_open_time: datetime | None
    last_input_open_time: datetime | None
    last_input_is_closed: bool | None
    true_range_count: int
    valid_true_range_count: int
    indicator_reason_code: str


def _atr14_diagnostic(
    bundle: StrategyDataBundle,
    prior_eval_time: datetime,
    strategy_params: StrategyParameters,
) -> _AtrDiagnostic:
    bundle_usable = bundle.is_usable
    daily_candles = bundle.daily.candles
    first = daily_candles[0] if daily_candles else None
    last = daily_candles[-1] if daily_candles else None
    true_ranges = compute_true_range(daily_candles) if daily_candles else []
    true_range_count = sum(item is not None for item in true_ranges)
    valid_true_range_count = sum(
        item is not None and item.is_finite() and item >= 0 for item in true_ranges
    )
    def result(present: bool, reason: str) -> _AtrDiagnostic:
        return _AtrDiagnostic(
            present=present,
            input_candle_count=len(daily_candles),
            first_input_open_time=first.open_time if first else None,
            last_input_open_time=last.open_time if last else None,
            last_input_is_closed=last.is_closed if last else None,
            true_range_count=true_range_count,
            valid_true_range_count=valid_true_range_count,
            indicator_reason_code=reason,
        )

    if not bundle_usable:
        return result(False, "BUNDLE_NOT_USABLE")
    if not daily_candles:
        return result(False, "NO_DAILY_INPUT")
    if any(not candle.is_closed for candle in daily_candles):
        return result(False, "OPEN_INPUT_CANDLE")
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
    if atr14 is not None and atr14 > 0:
        reason = "ATR_AVAILABLE"
        present = True
    elif strategy_eval.errors:
        reason = f"STRATEGY_{strategy_eval.errors[0].code.value}"
        present = False
    elif len(daily_candles) <= strategy_params.atr_period:
        reason = "ATR_WARMUP_INCOMPLETE"
        present = False
    elif atr14 is not None:
        reason = "ATR_NON_POSITIVE"
        present = False
    else:
        reason = "ATR_NOT_AVAILABLE"
        present = False
    return result(present, reason)


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
            atr_window=strategy_params.atr_period,
            indicator_reason_code="PRIOR_EVALUATION_TIME_MISSING",
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
    atr_diagnostic = (
        _atr14_diagnostic(bundle, prior_eval_time, strategy_params)
        if isinstance(bundle, StrategyDataBundle)
        else _AtrDiagnostic(
            present=False,
            input_candle_count=0,
            first_input_open_time=None,
            last_input_open_time=None,
            last_input_is_closed=None,
            true_range_count=0,
            valid_true_range_count=0,
            indicator_reason_code="UNTYPED_BUNDLE",
        )
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
        atr14_present=atr_diagnostic.present,
        market_data_ready=market_data_ready,
        prior_eval_time=prior_eval_time,
        evaluation_time=evaluation_time,
        input_candle_count=atr_diagnostic.input_candle_count,
        first_input_open_time=atr_diagnostic.first_input_open_time,
        last_input_open_time=atr_diagnostic.last_input_open_time,
        last_input_is_closed=atr_diagnostic.last_input_is_closed,
        true_range_count=atr_diagnostic.true_range_count,
        valid_true_range_count=atr_diagnostic.valid_true_range_count,
        atr_window=strategy_params.atr_period,
        indicator_reason_code=atr_diagnostic.indicator_reason_code,
    )
