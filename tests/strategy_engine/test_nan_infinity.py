"""Tests for NaN/Infinity rejection."""

from datetime import timedelta
from decimal import Decimal

from strategy_engine.models import Candle, CandleSeries, DataQualityStatus, Timeframe
from strategy_engine.validation import validate_candle_series

from tests.strategy_engine.conftest import build_flat_daily_series, daily_close_time


class TestNanInfinity:
    def test_nan_rejected_via_non_finite_check(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        bad = Candle.model_construct(
            symbol="BTC",
            timeframe=Timeframe.DAILY,
            open_time=candles[-1].open_time,
            close_time=daily_close_time(candles[-1].open_time),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("NaN"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        candles[-1] = bad
        s = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = bad.close_time + timedelta(seconds=5)
        status, errors = validate_candle_series(s, eval_time)
        assert status == DataQualityStatus.INVALID_DATA
        assert len(errors) > 0

    def test_infinity_rejected(self) -> None:
        series = build_flat_daily_series("BTC", 25)
        candles = list(series.candles)
        bad = Candle.model_construct(
            symbol="BTC",
            timeframe=Timeframe.DAILY,
            open_time=candles[-1].open_time,
            close_time=daily_close_time(candles[-1].open_time),
            open=Decimal("Infinity"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        candles[-1] = bad
        s = CandleSeries(symbol="BTC", timeframe=Timeframe.DAILY, candles=tuple(candles))
        eval_time = bad.close_time + timedelta(seconds=5)
        status, errors = validate_candle_series(s, eval_time)
        assert status == DataQualityStatus.INVALID_DATA
        assert len(errors) > 0
