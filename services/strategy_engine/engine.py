"""Strategy Engine V1 — main evaluation orchestrator."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.entry import (
    evaluate_breakout_setup,
    evaluate_pullback_setup,
    evaluate_volume_ok,
    resolve_entry_priority,
)
from strategy_engine.indicators import (
    compute_ema,
    compute_high20,
    compute_volume_ratio,
    compute_wilder_atr,
)
from strategy_engine.models import (
    CandleSeries,
    DataQualityStatus,
    EntrySetupResult,
    IndicatorSnapshot,
    ReasonCode,
    RegimeResult,
    SignalIntent,
    SignalIntentKind,
    StrategyError,
    StrategyEvaluation,
    StrategyParameters,
    Timeframe,
    TrendResult,
)
from strategy_engine.regime import evaluate_monthly_regime
from strategy_engine.stops import compute_initial_stop
from strategy_engine.trend import evaluate_weekly_trend
from strategy_engine.validation import check_warmup_complete, validate_candle_series


def _last_index(series: CandleSeries) -> int:
    return len(series.candles) - 1


def _closes(series: CandleSeries) -> list[Decimal]:
    return [c.close for c in series.candles]


def _highs(series: CandleSeries) -> list[Decimal]:
    return [c.high for c in series.candles]


def _volumes(series: CandleSeries) -> list[Decimal]:
    return [c.volume for c in series.candles]


def _empty_regime() -> RegimeResult:
    return RegimeResult(regime_long=False, reason_code=ReasonCode.RC_REJECT_WARMUP)


def _empty_trend() -> TrendResult:
    return TrendResult(trend_confirmed=False, reason_code=ReasonCode.RC_REJECT_WARMUP)


def _empty_setup() -> EntrySetupResult:
    return EntrySetupResult()


def _build_no_entry_evaluation(
    *,
    symbol: str,
    evaluation_time: datetime,
    parameters: StrategyParameters,
    data_quality_status: DataQualityStatus,
    signal_kind: SignalIntentKind,
    reason_codes: tuple[ReasonCode, ...],
    errors: tuple[StrategyError, ...],
    monthly_regime: RegimeResult | None = None,
    weekly_trend: TrendResult | None = None,
    indicators: IndicatorSnapshot | None = None,
    breakout_result: EntrySetupResult | None = None,
    pullback_result: EntrySetupResult | None = None,
    volume_ratio: Decimal | None = None,
    atr: Decimal | None = None,
) -> StrategyEvaluation:
    return StrategyEvaluation(
        symbol=symbol,
        evaluation_time=evaluation_time,
        strategy_version=STRATEGY_VERSION,
        parameters=parameters,
        monthly_regime=monthly_regime or _empty_regime(),
        weekly_trend=weekly_trend or _empty_trend(),
        breakout_result=breakout_result or _empty_setup(),
        pullback_result=pullback_result or _empty_setup(),
        indicators=indicators or IndicatorSnapshot(evaluation_index=-1),
        volume_ratio=volume_ratio,
        atr=atr,
        selected_entry_type=None,
        signal_intent=SignalIntent(
            kind=signal_kind,
            primary_reason_code=reason_codes[0] if reason_codes else None,
        ),
        reason_codes=reason_codes,
        data_quality_status=data_quality_status,
        errors=errors,
    )


class StrategyEngine:
    """
    Deterministic Strategy V1 evaluation engine.

    No system clock, network, database, or mutable global state.
    """

    def evaluate(
        self,
        daily: CandleSeries,
        weekly: CandleSeries,
        monthly: CandleSeries,
        evaluation_time: datetime,
        parameters: StrategyParameters | None = None,
    ) -> StrategyEvaluation:
        """
        Evaluate strategy at evaluation_time using closed candles only.

        All three series must share the same symbol.
        """
        params = parameters or StrategyParameters()
        symbol = daily.symbol
        all_errors: list[StrategyError] = []

        for series in (weekly, monthly):
            if series.symbol != symbol:
                return _build_no_entry_evaluation(
                    symbol=symbol,
                    evaluation_time=evaluation_time,
                    parameters=params,
                    data_quality_status=DataQualityStatus.INVALID_DATA,
                    signal_kind=SignalIntentKind.INVALID_DATA,
                    reason_codes=(ReasonCode.RC_REJECT_DATA,),
                    errors=(
                        StrategyError(
                            code=ReasonCode.RC_REJECT_DATA,
                            message="Symbol mismatch across timeframes",
                            details={"daily": daily.symbol, "other": series.symbol},
                        ),
                    ),
                )

        daily_status, daily_errors = validate_candle_series(
            daily, evaluation_time, expected_timeframe=Timeframe.DAILY
        )
        weekly_status, weekly_errors = validate_candle_series(
            weekly, evaluation_time, expected_timeframe=Timeframe.WEEKLY
        )
        monthly_status, monthly_errors = validate_candle_series(
            monthly, evaluation_time, expected_timeframe=Timeframe.MONTHLY
        )

        all_errors.extend(daily_errors)
        all_errors.extend(weekly_errors)
        all_errors.extend(monthly_errors)

        if DataQualityStatus.INVALID_DATA in (
            daily_status,
            weekly_status,
            monthly_status,
        ):
            return _build_no_entry_evaluation(
                symbol=symbol,
                evaluation_time=evaluation_time,
                parameters=params,
                data_quality_status=DataQualityStatus.INVALID_DATA,
                signal_kind=SignalIntentKind.INVALID_DATA,
                reason_codes=(ReasonCode.RC_REJECT_DATA,),
                errors=tuple(all_errors),
            )

        if (
            daily_status == DataQualityStatus.INSUFFICIENT_HISTORY
            or weekly_status != DataQualityStatus.OK
            or monthly_status != DataQualityStatus.OK
        ):
            if not check_warmup_complete(
                daily.length, weekly.length, monthly.length, params
            ):
                return _build_no_entry_evaluation(
                    symbol=symbol,
                    evaluation_time=evaluation_time,
                    parameters=params,
                    data_quality_status=DataQualityStatus.INSUFFICIENT_HISTORY,
                    signal_kind=SignalIntentKind.INSUFFICIENT_HISTORY,
                    reason_codes=(ReasonCode.RC_REJECT_WARMUP,),
                    errors=tuple(all_errors),
                )

        t = _last_index(daily)
        daily_closes = _closes(daily)
        daily_highs = _highs(daily)
        daily_volumes = _volumes(daily)
        candle_t = daily.candles[t]

        ema20_daily_series = compute_ema(daily_closes, params.daily_ema_period)
        atr14_series = compute_wilder_atr(daily.candles, params.atr_period)
        volume_ratio_series = compute_volume_ratio(
            daily_volumes, params.volume_sma_period
        )
        high20_series = compute_high20(daily_highs, params.breakout_lookback)

        weekly_closes = _closes(weekly)
        ema20_weekly_series = compute_ema(weekly_closes, params.weekly_ema_fast)
        ema50_weekly_series = compute_ema(weekly_closes, params.weekly_ema_slow)
        w_idx = _last_index(weekly)

        monthly_closes = _closes(monthly)
        ema20_monthly_series = compute_ema(monthly_closes, params.monthly_ema_period)
        m_idx = _last_index(monthly)

        ema20_daily = ema20_daily_series[t]
        ema20_daily_prev = ema20_daily_series[t - 1] if t >= 1 else None
        atr14 = atr14_series[t]
        volume_ratio = volume_ratio_series[t]
        high20 = high20_series[t]
        ema20_weekly = ema20_weekly_series[w_idx]
        ema50_weekly = ema50_weekly_series[w_idx]
        ema20_monthly = ema20_monthly_series[m_idx]
        monthly_close = monthly_closes[m_idx]

        indicators = IndicatorSnapshot(
            evaluation_index=t,
            ema20_daily=ema20_daily,
            ema20_weekly=ema20_weekly,
            ema50_weekly=ema50_weekly,
            ema20_monthly=ema20_monthly,
            atr14_daily=atr14,
            volume_ratio=volume_ratio,
            high20=high20,
            monthly_close=monthly_close,
        )

        if (
            ema20_daily is None
            or atr14 is None
            or atr14 <= 0
            or volume_ratio is None
            or ema20_weekly is None
            or ema50_weekly is None
            or ema20_monthly is None
        ):
            return _build_no_entry_evaluation(
                symbol=symbol,
                evaluation_time=evaluation_time,
                parameters=params,
                data_quality_status=DataQualityStatus.INSUFFICIENT_HISTORY,
                signal_kind=SignalIntentKind.INSUFFICIENT_HISTORY,
                reason_codes=(ReasonCode.RC_REJECT_WARMUP,),
                errors=tuple(all_errors),
                monthly_regime=evaluate_monthly_regime(monthly_close, ema20_monthly),
                weekly_trend=evaluate_weekly_trend(ema20_weekly, ema50_weekly),
                indicators=indicators,
                volume_ratio=volume_ratio,
                atr=atr14,
            )

        regime = evaluate_monthly_regime(monthly_close, ema20_monthly)
        trend = evaluate_weekly_trend(ema20_weekly, ema50_weekly)
        volume_ok = evaluate_volume_ok(volume_ratio, params.volume_ratio_min)

        breakout_result = evaluate_breakout_setup(
            close_t=candle_t.close,
            high20=high20,
            ema20_daily=ema20_daily,
            regime=regime,
            trend=trend,
            volume_ok=volume_ok,
        )

        close_prev = daily_closes[t - 1] if t >= 1 else None
        pullback_result = evaluate_pullback_setup(
            close_t=candle_t.close,
            low_t=candle_t.low,
            close_prev=close_prev,
            ema20_daily=ema20_daily,
            ema20_daily_prev=ema20_daily_prev,
            regime=regime,
            trend=trend,
            volume_ok=volume_ok,
            params=params,
        )

        entry_price = candle_t.close
        stop_initial = compute_initial_stop(entry_price, atr14, params)

        selected_entry_type, primary_reason = resolve_entry_priority(
            breakout_result, pullback_result, entry_price, stop_initial
        )

        if selected_entry_type is not None and primary_reason is not None:
            if entry_price <= stop_initial:
                return _build_no_entry_evaluation(
                    symbol=symbol,
                    evaluation_time=evaluation_time,
                    parameters=params,
                    data_quality_status=DataQualityStatus.OK,
                    signal_kind=SignalIntentKind.NO_ENTRY,
                    reason_codes=(ReasonCode.RC_REJECT_DATA,),
                    errors=tuple(all_errors),
                    monthly_regime=regime,
                    weekly_trend=trend,
                    indicators=indicators,
                    breakout_result=breakout_result,
                    pullback_result=pullback_result,
                    volume_ratio=volume_ratio,
                    atr=atr14,
                )

            return StrategyEvaluation(
                symbol=symbol,
                evaluation_time=evaluation_time,
                strategy_version=STRATEGY_VERSION,
                parameters=params,
                monthly_regime=regime,
                weekly_trend=trend,
                breakout_result=breakout_result,
                pullback_result=pullback_result,
                indicators=indicators,
                volume_ratio=volume_ratio,
                atr=atr14,
                selected_entry_type=selected_entry_type,
                signal_intent=SignalIntent(
                    kind=SignalIntentKind.LONG_ENTRY,
                    entry_type=selected_entry_type,
                    entry_price=entry_price,
                    stop_initial=stop_initial,
                    primary_reason_code=primary_reason,
                ),
                reason_codes=(primary_reason,),
                data_quality_status=DataQualityStatus.OK,
                errors=tuple(all_errors),
            )

        reason_codes: list[ReasonCode] = []
        if not regime.regime_long and regime.reason_code:
            reason_codes.append(regime.reason_code)
        if not trend.trend_confirmed and trend.reason_code:
            reason_codes.append(trend.reason_code)
        if not volume_ok:
            reason_codes.append(ReasonCode.RC_REJECT_VOLUME)
        if not reason_codes:
            reason_codes.append(ReasonCode.RC_REJECT_NO_SIGNAL)

        return StrategyEvaluation(
            symbol=symbol,
            evaluation_time=evaluation_time,
            strategy_version=STRATEGY_VERSION,
            parameters=params,
            monthly_regime=regime,
            weekly_trend=trend,
            breakout_result=breakout_result,
            pullback_result=pullback_result,
            indicators=indicators,
            volume_ratio=volume_ratio,
            atr=atr14,
            selected_entry_type=None,
            signal_intent=SignalIntent(
                kind=SignalIntentKind.NO_ENTRY,
                primary_reason_code=reason_codes[-1],
            ),
            reason_codes=tuple(reason_codes),
            data_quality_status=DataQualityStatus.OK,
            errors=tuple(all_errors),
        )
