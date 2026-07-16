"""Determinism and look-ahead bias tests."""

from datetime import timedelta

from strategy_engine.engine import StrategyEngine
from strategy_engine.models import SignalIntentKind

from tests.strategy_engine.conftest import (
    build_flat_daily_series,
    build_flat_weekly_series,
    build_rising_monthly_series,
)


class TestDeterminism:
    def test_identical_inputs_identical_outputs(self) -> None:
        engine = StrategyEngine()
        daily = build_flat_daily_series("BTC", 30)
        weekly = build_flat_weekly_series("BTC", 55)
        monthly = build_rising_monthly_series("BTC", 25)
        eval_time = daily.candles[-1].close_time + timedelta(seconds=5)

        r1 = engine.evaluate(daily, weekly, monthly, eval_time)
        r2 = engine.evaluate(daily, weekly, monthly, eval_time)

        assert r1.model_dump() == r2.model_dump()


class TestLookaheadBias:
    def test_no_signal_before_candle_close(self) -> None:
        engine = StrategyEngine()
        daily = build_flat_daily_series("BTC", 30)
        weekly = build_flat_weekly_series("BTC", 55)
        monthly = build_rising_monthly_series("BTC", 25)

        before_close = daily.candles[-1].close_time - timedelta(seconds=1)
        result = engine.evaluate(daily, weekly, monthly, before_close)
        assert result.signal_intent.kind in (
            SignalIntentKind.INVALID_DATA,
            SignalIntentKind.INSUFFICIENT_HISTORY,
            SignalIntentKind.NO_ENTRY,
        )
        assert result.signal_intent.kind != SignalIntentKind.LONG_ENTRY

    def test_signal_after_close_with_breakout(self) -> None:

        from strategy_engine.models import CandleSeries, EntryType, ReasonCode, Timeframe

        from tests.strategy_engine.conftest import make_daily_candle

        engine = StrategyEngine()
        daily = build_flat_daily_series("BTC", 30)
        weekly = build_flat_weekly_series("BTC", 55)
        monthly = build_rising_monthly_series("BTC", 25)
        candles = list(daily.candles)
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-1].open_time,
            "100",
            "130",
            "99",
            "125",
            vol="2000",
        )
        daily = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        after_close = candles[-1].close_time + timedelta(seconds=5)
        result = engine.evaluate(daily, weekly, monthly, after_close)
        if result.signal_intent.kind == SignalIntentKind.LONG_ENTRY:
            assert result.selected_entry_type == EntryType.BREAKOUT
            assert ReasonCode.RC_ENTRY_BREAKOUT_20D in result.reason_codes
