"""Unit tests for candle validation."""

from datetime import timedelta

from strategy_engine.models import DataQualityStatus, ReasonCode, StrategyParameters, Timeframe
from strategy_engine.validation import min_candles_for_warmup, validate_candle_series

from tests.strategy_engine.conftest import (
    build_flat_daily_series,
    make_daily_candle,
)


class TestValidation:
    def test_valid_series_ok(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        eval_time = series.candles[-1].close_time + timedelta(seconds=5)
        status, errors = validate_candle_series(series, eval_time)
        assert status == DataQualityStatus.OK
        assert errors == ()

    def test_insufficient_history(self) -> None:
        series = build_flat_daily_series("BTC", 10)
        eval_time = series.candles[-1].close_time + timedelta(seconds=5)
        status, errors = validate_candle_series(series, eval_time)
        assert status == DataQualityStatus.INSUFFICIENT_HISTORY
        assert errors[0].code == ReasonCode.RC_REJECT_WARMUP

    def test_open_candle_rejected(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-1].open_time,
            "100",
            "102",
            "99",
            "101",
            is_closed=False,
        )
        from strategy_engine.models import CandleSeries, Timeframe

        bad = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        status, errors = validate_candle_series(bad, eval_time)
        assert status == DataQualityStatus.INVALID_DATA

    def test_duplicate_timestamp(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-2].open_time,
            "100",
            "102",
            "99",
            "101",
        )
        from strategy_engine.models import CandleSeries, Timeframe

        bad = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        status, _ = validate_candle_series(bad, eval_time)
        assert status == DataQualityStatus.INVALID_DATA

    def test_unsorted_candles(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        candles[-2], candles[-1] = candles[-1], candles[-2]
        from strategy_engine.models import CandleSeries, Timeframe

        bad = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        status, _ = validate_candle_series(bad, eval_time)
        assert status == DataQualityStatus.INVALID_DATA

    def test_invalid_ohlc_high_below_low(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-1].open_time,
            "100",
            "90",
            "95",
            "98",
        )
        from strategy_engine.models import CandleSeries, Timeframe

        bad = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        status, _ = validate_candle_series(bad, eval_time)
        assert status == DataQualityStatus.INVALID_DATA

    def test_negative_volume(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        candles[-1] = make_daily_candle(
            "BTC",
            candles[-1].open_time,
            "100",
            "102",
            "99",
            "101",
            vol="-1",
        )
        from strategy_engine.models import CandleSeries, Timeframe

        bad = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = candles[-1].close_time + timedelta(seconds=5)
        status, _ = validate_candle_series(bad, eval_time)
        assert status == DataQualityStatus.INVALID_DATA

    def test_evaluation_before_close(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        eval_time = series.candles[-1].close_time - timedelta(seconds=1)
        status, _ = validate_candle_series(series, eval_time)
        assert status == DataQualityStatus.INVALID_DATA

    def test_min_candles_for_warmup_uses_params(self) -> None:
        params = StrategyParameters(breakout_lookback=30, daily_ema_period=25)
        assert min_candles_for_warmup(Timeframe.DAILY, params) == 31
        assert min_candles_for_warmup(Timeframe.WEEKLY, params) == 50
        assert min_candles_for_warmup(Timeframe.MONTHLY, params) == 20
