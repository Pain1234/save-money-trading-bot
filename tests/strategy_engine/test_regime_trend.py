"""Unit tests for regime and trend filters."""

from decimal import Decimal

from strategy_engine.models import ReasonCode
from strategy_engine.regime import evaluate_monthly_regime
from strategy_engine.trend import evaluate_weekly_trend


class TestMonthlyRegime:
    def test_valid_regime_long(self) -> None:
        result = evaluate_monthly_regime(Decimal("110"), Decimal("100"))
        assert result.regime_long is True
        assert result.reason_code is None

    def test_invalid_regime(self) -> None:
        result = evaluate_monthly_regime(Decimal("90"), Decimal("100"))
        assert result.regime_long is False
        assert result.reason_code == ReasonCode.RC_REJECT_REGIME

    def test_regime_equal_not_long(self) -> None:
        result = evaluate_monthly_regime(Decimal("100"), Decimal("100"))
        assert result.regime_long is False


class TestWeeklyTrend:
    def test_trend_confirmed(self) -> None:
        result = evaluate_weekly_trend(Decimal("110"), Decimal("100"))
        assert result.trend_confirmed is True
        assert result.reason_code is None

    def test_trend_not_confirmed(self) -> None:
        result = evaluate_weekly_trend(Decimal("90"), Decimal("100"))
        assert result.trend_confirmed is False
        assert result.reason_code == ReasonCode.RC_REJECT_TREND

    def test_weekly_break_does_not_imply_exit(self) -> None:
        """V1: trend break blocks entries only — no exit signal from trend module."""
        result = evaluate_weekly_trend(Decimal("80"), Decimal("100"))
        assert result.trend_confirmed is False
        assert result.reason_code == ReasonCode.RC_REJECT_TREND
