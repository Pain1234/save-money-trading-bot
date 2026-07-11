"""Unit tests for technical indicators."""

from decimal import Decimal

from strategy_engine.indicators import (
    compute_ema,
    compute_high20,
    compute_true_range,
    compute_volume_ratio,
    compute_wilder_atr,
)

from tests.strategy_engine.conftest import dt, make_daily_candle


class TestEMA:
    def test_ema_reference_values_period_3(self) -> None:
        closes = [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")]
        ema = compute_ema(closes, 3)
        assert ema[0] is None
        assert ema[1] is None
        assert ema[2] == Decimal("11")
        assert ema[3] == Decimal("12")
        assert ema[4] == Decimal("13")

    def test_ema_insufficient_history(self) -> None:
        closes = [Decimal("10"), Decimal("11")]
        ema = compute_ema(closes, 20)
        assert all(v is None for v in ema)


class TestWilderATR:
    def test_atr_reference_values(self) -> None:
        symbol = "BTC"
        candles = []
        data = [
            ("100", "105", "95", "102"),
            ("102", "108", "100", "106"),
            ("106", "110", "104", "108"),
            ("108", "112", "106", "110"),
            ("110", "115", "108", "112"),
            ("112", "116", "109", "114"),
            ("114", "118", "111", "116"),
            ("116", "120", "113", "118"),
            ("118", "122", "115", "120"),
            ("120", "125", "118", "123"),
            ("123", "128", "121", "126"),
            ("126", "130", "124", "128"),
            ("128", "132", "126", "130"),
            ("130", "135", "128", "133"),
            ("133", "138", "131", "136"),
            ("136", "140", "134", "138"),
        ]
        for i, (o, h, low, c) in enumerate(data):
            candles.append(
                make_daily_candle(symbol, dt(2024, 1, 1 + i), o, h, low, c)
            )

        tr = compute_true_range(candles)
        assert tr[0] is None
        assert tr[1] == Decimal("8")

        atr = compute_wilder_atr(candles, 14)
        assert atr[13] is None
        assert atr[14] == Decimal("95") / Decimal("14")
        assert atr[15] == (
            (Decimal("95") / Decimal("14")) * Decimal("13") + Decimal("6")
        ) / Decimal("14")


class TestVolumeRatio:
    def test_volume_ratio_constant_volume(self) -> None:
        volumes = [Decimal("100")] * 25
        ratios = compute_volume_ratio(volumes, 20)
        assert ratios[18] is None
        assert ratios[19] == Decimal("1")
        assert ratios[24] == Decimal("1")

    def test_volume_ratio_doubled_current(self) -> None:
        # V[t] = 2 × VolSMA20[t] with 19 prior volumes at 100 → V[t] = 1900/9
        volumes = [Decimal("100")] * 20
        volumes.append(Decimal("1900") / Decimal("9"))
        ratios = compute_volume_ratio(volumes, 20)
        assert ratios[20] is not None
        assert ratios[20] >= Decimal("1.99")
        assert ratios[20] <= Decimal("2.01")


class TestHigh20:
    def test_high20_excludes_current_candle(self) -> None:
        highs = [Decimal(str(i)) for i in range(1, 26)]
        result = compute_high20(highs, 20)
        assert result[20] == Decimal("20")
        assert result[24] == Decimal("24")

    def test_high20_current_not_included(self) -> None:
        highs = [Decimal("10")] * 20 + [Decimal("999")]
        result = compute_high20(highs, 20)
        t = 20
        assert result[t] == Decimal("10")
        assert result[t] != Decimal("999")

    def test_high20_insufficient_history(self) -> None:
        highs = [Decimal("10")] * 15
        result = compute_high20(highs, 20)
        assert all(v is None for v in result)
