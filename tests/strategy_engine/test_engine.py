"""Integration tests for StrategyEngine.evaluate."""

from datetime import timedelta
from decimal import Decimal

from strategy_engine.engine import StrategyEngine
from strategy_engine.models import (
    CandleSeries,
    DataQualityStatus,
    EntryType,
    ReasonCode,
    SignalIntentKind,
    Timeframe,
)

from tests.strategy_engine.conftest import (
    build_flat_daily_series,
    build_flat_weekly_series,
    build_rising_monthly_series,
    build_rising_weekly_series,
    make_daily_candle,
    make_monthly_candle,
)


def _warmup_series(symbol: str = "BTC") -> tuple[CandleSeries, CandleSeries, CandleSeries]:
    daily = build_flat_daily_series(symbol, 30, base_price="100", base_volume="1000")
    weekly = build_rising_weekly_series(symbol, 55, start_price=Decimal("100"))
    monthly = build_rising_monthly_series(symbol, 25, start_price=Decimal("100"))
    return daily, weekly, monthly


class TestStrategyEngine:
    def test_insufficient_history(self) -> None:
        engine = StrategyEngine()
        daily = build_flat_daily_series("BTC", 10)
        weekly = build_flat_weekly_series("BTC", 10)
        monthly = build_rising_monthly_series("BTC", 10)
        eval_time = daily.candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, eval_time)
        assert result.signal_intent.kind == SignalIntentKind.INSUFFICIENT_HISTORY
        assert ReasonCode.RC_REJECT_WARMUP in result.reason_codes

    def test_no_entry_flat_market(self) -> None:
        engine = StrategyEngine()
        daily, weekly, monthly = _warmup_series()
        eval_time = daily.candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, eval_time)
        assert result.signal_intent.kind == SignalIntentKind.NO_ENTRY
        assert result.data_quality_status == DataQualityStatus.OK

    def test_breakout_entry(self) -> None:
        engine = StrategyEngine()
        daily, weekly, monthly = _warmup_series()
        candles = list(daily.candles)
        last = candles[-1]
        candles[-1] = make_daily_candle(
            "BTC",
            last.open_time,
            "100",
            "130",
            "99",
            "125",
            vol="2000",
        )
        daily = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, eval_time)
        assert result.signal_intent.kind == SignalIntentKind.LONG_ENTRY
        assert result.selected_entry_type == EntryType.BREAKOUT
        assert ReasonCode.RC_ENTRY_BREAKOUT_20D in result.reason_codes
        assert result.atr is not None
        assert result.signal_intent.stop_initial == Decimal("125") - Decimal("2.5") * result.atr

    def test_simultaneous_breakout_and_pullback_priority(self) -> None:
        engine = StrategyEngine()
        daily, weekly, monthly = _warmup_series()
        candles = list(daily.candles)
        prev = candles[-2]
        ema_approx = Decimal("100")
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-1].open_time,
            "100",
            "130",
            str(ema_approx),
            "125",
            vol="2000",
        )
        candles[-2] = make_daily_candle(
            "BTC",
            prev.open_time,
            "100",
            "102",
            "99",
            "101",
            vol="1000",
        )
        daily = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, eval_time)
        if result.breakout_result.breakout_entry and result.pullback_result.pullback_entry:
            assert result.selected_entry_type == EntryType.BREAKOUT
            assert result.reason_codes == (ReasonCode.RC_ENTRY_BREAKOUT_20D,)
            assert ReasonCode.RC_ENTRY_PULLBACK_EMA20 not in result.reason_codes

    def test_reject_regime_when_monthly_bearish(self) -> None:
        engine = StrategyEngine()
        daily = build_flat_daily_series("BTC", 30)
        weekly = build_flat_weekly_series("BTC", 55)
        mc = [
            make_monthly_candle("BTC", 2020 + i // 12, (i % 12) + 1, "200", "200", "200", "200")
            for i in range(24)
        ]
        mc.append(make_monthly_candle("BTC", 2022, 1, "10", "10", "10", "10"))
        monthly = CandleSeries(
            symbol="BTC", timeframe=Timeframe.MONTHLY, candles=tuple(mc)
        )
        eval_time = daily.candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, eval_time)
        assert result.monthly_regime.regime_long is False
        assert result.signal_intent.kind == SignalIntentKind.NO_ENTRY
        assert ReasonCode.RC_REJECT_REGIME in result.reason_codes

    def test_volume_ratio_reject_below_baseline(self) -> None:
        engine = StrategyEngine()
        daily, weekly, monthly = _warmup_series()
        candles = list(daily.candles)
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-1].open_time,
            "100",
            "130",
            "99",
            "125",
            vol="500",
        )
        daily = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, eval_time)
        assert ReasonCode.RC_REJECT_VOLUME in result.reason_codes

    def test_open_weekly_candle_is_rejected_fail_closed(self) -> None:
        engine = StrategyEngine()
        daily, weekly, monthly = _warmup_series()
        candles = list(weekly.candles)
        candles[-1] = candles[-1].model_copy(update={"is_closed": False})
        weekly = weekly.model_copy(update={"candles": tuple(candles)})

        result = engine.evaluate(
            daily,
            weekly,
            monthly,
            daily.candles[-1].close_time + timedelta(seconds=5),
        )

        assert result.data_quality_status == DataQualityStatus.INVALID_DATA
        assert result.signal_intent.kind == SignalIntentKind.INVALID_DATA
        assert result.reason_codes == (ReasonCode.RC_REJECT_DATA,)

    def test_future_monthly_candle_is_rejected_fail_closed(self) -> None:
        engine = StrategyEngine()
        daily, weekly, monthly = _warmup_series()
        evaluation_time = daily.candles[-1].close_time + timedelta(seconds=5)
        candles = list(monthly.candles)
        candles[-1] = candles[-1].model_copy(
            update={"close_time": evaluation_time + timedelta(days=1)}
        )
        monthly = monthly.model_copy(update={"candles": tuple(candles)})

        result = engine.evaluate(daily, weekly, monthly, evaluation_time)

        assert result.data_quality_status == DataQualityStatus.INVALID_DATA
        assert result.signal_intent.kind == SignalIntentKind.INVALID_DATA
        assert result.reason_codes == (ReasonCode.RC_REJECT_DATA,)
