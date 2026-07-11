# ruff: noqa: E402
"""Shared fixtures for backtester tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from backtester.models import (
    BacktestConfig,
    FeeModel,
    FundingEvent,
    FundingModel,
    HistoricalDataBundle,
    SlippageModel,
)
from risk_engine.models import RiskParameters, SymbolConstraints
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import (
    Candle,
    DataQualityStatus,
    EntrySetupResult,
    EntryType,
    IndicatorSnapshot,
    ReasonCode,
    RegimeResult,
    SignalIntent,
    SignalIntentKind,
    StrategyEvaluation,
    StrategyParameters,
    Timeframe,
    TrendResult,
)

UTC = UTC

DEFAULT_CONSTRAINTS = SymbolConstraints(
    quantity_step=Decimal("0.001"),
    minimum_quantity=Decimal("0.001"),
    minimum_notional=Decimal("10"),
    price_tick_size=Decimal("0.01"),
)


def dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


def daily_close_time(open_time: datetime) -> datetime:
    return open_time.replace(hour=23, minute=59, second=59)


def make_daily(
    symbol: str,
    open_time: datetime,
    o: str,
    h: str,
    low: str,
    c: str,
    *,
    is_closed: bool = True,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.DAILY,
        open_time=open_time,
        close_time=daily_close_time(open_time),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


def make_weekly(
    symbol: str,
    open_time: datetime,
    o: str,
    h: str,
    low: str,
    c: str,
    *,
    is_closed: bool = True,
) -> Candle:
    close_time = open_time + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.WEEKLY,
        open_time=open_time,
        close_time=close_time,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("5000"),
        is_closed=is_closed,
    )


def make_monthly(
    symbol: str,
    year: int,
    month: int,
    price: str = "100",
    *,
    is_closed: bool = True,
) -> Candle:
    open_time = dt(year, month, 1)
    if month == 12:
        next_month = dt(year + 1, 1, 1)
    else:
        next_month = dt(year, month + 1, 1)
    close_time = next_month - timedelta(seconds=1)
    p = Decimal(price)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.MONTHLY,
        open_time=open_time,
        close_time=close_time,
        open=p,
        high=p,
        low=p,
        close=p,
        volume=Decimal("20000"),
        is_closed=is_closed,
    )


def flat_daily_series(symbol: str, count: int, price: str = "100", start: datetime | None = None):
    start = start or dt(2024, 1, 1)
    return tuple(
        make_daily(symbol, start + timedelta(days=i), price, price, price, price)
        for i in range(count)
    )


def make_config(
    symbols: tuple[str, ...] = ("BTC",),
    initial_cash: str = "100000",
    *,
    fee_entry: str = "0.0005",
    fee_exit: str = "0.0005",
    slippage_bps: str = "5",
    funding_enabled: bool = False,
    risk_params: RiskParameters | None = None,
    initial_processed: tuple[str, ...] = (),
) -> BacktestConfig:
    constraints = {s: DEFAULT_CONSTRAINTS for s in symbols}
    return BacktestConfig(
        symbols=symbols,
        initial_cash=Decimal(initial_cash),
        risk_params=risk_params or RiskParameters(),
        fee_model=FeeModel(
            entry_fee_rate=Decimal(fee_entry),
            exit_fee_rate=Decimal(fee_exit),
        ),
        slippage_model=SlippageModel(slippage_bps=Decimal(slippage_bps)),
        funding_model=FundingModel(enabled=funding_enabled),
        symbol_constraints=constraints,
        initial_processed_intent_ids=initial_processed,
    )


def make_bundle(
    symbol: str = "BTC",
    daily: tuple | None = None,
    weekly: tuple | None = None,
    monthly: tuple | None = None,
    funding: tuple[FundingEvent, ...] | None = None,
) -> HistoricalDataBundle:
    daily = daily or flat_daily_series(symbol, 30)
    weekly = weekly or (make_weekly(symbol, dt(2023, 12, 25), "100", "105", "95", "100"),)
    monthly = monthly or (make_monthly(symbol, 2023, 12, "100"),)
    return HistoricalDataBundle(
        daily={symbol: daily},
        weekly={symbol: weekly},
        monthly={symbol: monthly},
        funding={symbol: funding or ()},
    )


def _base_evaluation(symbol: str, eval_time: datetime) -> dict:
    params = StrategyParameters()
    return dict(
        symbol=symbol,
        evaluation_time=eval_time,
        strategy_version=STRATEGY_VERSION,
        parameters=params,
        monthly_regime=RegimeResult(regime_long=True),
        weekly_trend=TrendResult(trend_confirmed=True),
        breakout_result=EntrySetupResult(),
        pullback_result=EntrySetupResult(),
        indicators=IndicatorSnapshot(evaluation_index=0),
        data_quality_status=DataQualityStatus.OK,
    )


def make_no_entry_eval(symbol: str, eval_time: datetime) -> StrategyEvaluation:
    return StrategyEvaluation(
        **_base_evaluation(symbol, eval_time),
        signal_intent=SignalIntent(kind=SignalIntentKind.NO_ENTRY),
        reason_codes=(ReasonCode.RC_REJECT_NO_SIGNAL,),
    )


def make_long_entry_eval(
    symbol: str,
    eval_time: datetime,
    *,
    entry_price: str = "100",
    stop: str = "90",
    atr: str = "2",
    entry_type: EntryType = EntryType.BREAKOUT,
    reason_codes: tuple[ReasonCode, ...] = (ReasonCode.RC_ENTRY_BREAKOUT_20D,),
) -> StrategyEvaluation:
    return StrategyEvaluation(
        **_base_evaluation(symbol, eval_time),
        atr=Decimal(atr),
        selected_entry_type=entry_type,
        signal_intent=SignalIntent(
            kind=SignalIntentKind.LONG_ENTRY,
            entry_type=entry_type,
            entry_price=Decimal(entry_price),
            stop_initial=Decimal(stop),
            primary_reason_code=reason_codes[0],
        ),
        reason_codes=reason_codes,
    )


def make_insufficient_history_eval(symbol: str, eval_time: datetime) -> StrategyEvaluation:
    base = _base_evaluation(symbol, eval_time)
    base["data_quality_status"] = DataQualityStatus.INSUFFICIENT_HISTORY
    return StrategyEvaluation(
        **base,
        signal_intent=SignalIntent(kind=SignalIntentKind.INSUFFICIENT_HISTORY),
        reason_codes=(ReasonCode.RC_REJECT_WARMUP,),
    )
