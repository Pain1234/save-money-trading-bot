"""Unit tests for entry setups, volume filter, and signal priority."""

from decimal import Decimal

from strategy_engine.entry import (
    evaluate_breakout_setup,
    evaluate_pullback_setup,
    evaluate_volume_ok,
    resolve_entry_priority,
)
from strategy_engine.models import (
    EntrySetupResult,
    EntryType,
    ReasonCode,
    RegimeResult,
    StrategyParameters,
    TrendResult,
)


def _regime_long() -> RegimeResult:
    return RegimeResult(regime_long=True, monthly_close=Decimal("200"), ema20_monthly=Decimal("100"))


def _trend_ok() -> TrendResult:
    return TrendResult(trend_confirmed=True, ema20_weekly=Decimal("110"), ema50_weekly=Decimal("100"))


class TestVolumeFilter:
    def test_volume_ratio_exactly_one(self) -> None:
        assert evaluate_volume_ok(Decimal("1.00"), Decimal("1.00")) is True

    def test_volume_ratio_just_below_one(self) -> None:
        assert evaluate_volume_ok(Decimal("0.9999"), Decimal("1.00")) is False

    def test_default_baseline_is_one(self) -> None:
        params = StrategyParameters()
        assert params.volume_ratio_min == Decimal("1.00")


class TestBreakout:
    def test_valid_breakout(self) -> None:
        result = evaluate_breakout_setup(
            close_t=Decimal("105"),
            high20=Decimal("100"),
            ema20_daily=Decimal("95"),
            regime=_regime_long(),
            trend=_trend_ok(),
            volume_ok=True,
        )
        assert result.breakout_entry is True

    def test_breakout_excludes_current_from_high20(self) -> None:
        result = evaluate_breakout_setup(
            close_t=Decimal("105"),
            high20=Decimal("100"),
            ema20_daily=Decimal("95"),
            regime=_regime_long(),
            trend=_trend_ok(),
            volume_ok=True,
        )
        assert result.breakout_price_condition is True
        assert result.high20 == Decimal("100")


class TestPullback:
    def test_valid_pullback_p1_to_p6(self) -> None:
        params = StrategyParameters()
        ema = Decimal("100")
        ema_upper = ema * (Decimal("1") + params.pullback_ema_tolerance)
        result = evaluate_pullback_setup(
            close_t=Decimal("102"),
            low_t=ema_upper,
            close_prev=Decimal("101"),
            ema20_daily=ema,
            ema20_daily_prev=Decimal("99"),
            regime=_regime_long(),
            trend=_trend_ok(),
            volume_ok=True,
            params=params,
        )
        assert result.pullback_entry is True
        pc = result.pullback_conditions
        assert pc.p1_close_above_ema is True
        assert pc.p2_low_touches_ema is True
        assert pc.p3_prior_close_above_ema is True
        assert pc.p4_regime_long is True
        assert pc.p5_trend_confirmed is True
        assert pc.p6_volume_ok is True

    def test_pullback_fails_p1_close_not_above_ema(self) -> None:
        params = StrategyParameters()
        result = evaluate_pullback_setup(
            close_t=Decimal("99"),
            low_t=Decimal("98"),
            close_prev=Decimal("101"),
            ema20_daily=Decimal("100"),
            ema20_daily_prev=Decimal("99"),
            regime=_regime_long(),
            trend=_trend_ok(),
            volume_ok=True,
            params=params,
        )
        assert result.pullback_entry is False
        assert result.pullback_conditions.p1_close_above_ema is False

    def test_pullback_fails_p2_low_not_touching(self) -> None:
        params = StrategyParameters()
        result = evaluate_pullback_setup(
            close_t=Decimal("110"),
            low_t=Decimal("108"),
            close_prev=Decimal("101"),
            ema20_daily=Decimal("100"),
            ema20_daily_prev=Decimal("99"),
            regime=_regime_long(),
            trend=_trend_ok(),
            volume_ok=True,
            params=params,
        )
        assert result.pullback_entry is False
        assert result.pullback_conditions.p2_low_touches_ema is False

    def test_pullback_fails_p3_prior_close(self) -> None:
        params = StrategyParameters()
        result = evaluate_pullback_setup(
            close_t=Decimal("102"),
            low_t=Decimal("100"),
            close_prev=Decimal("98"),
            ema20_daily=Decimal("100"),
            ema20_daily_prev=Decimal("99"),
            regime=_regime_long(),
            trend=_trend_ok(),
            volume_ok=True,
            params=params,
        )
        assert result.pullback_entry is False
        assert result.pullback_conditions.p3_prior_close_above_ema is False


class TestSignalPriority:
    def test_breakout_and_pullback_single_intent(self) -> None:
        breakout = EntrySetupResult(breakout_entry=True)
        pullback = EntrySetupResult(pullback_entry=True)
        entry_type, reason = resolve_entry_priority(
            breakout, pullback, Decimal("100"), Decimal("90")
        )
        assert entry_type == EntryType.BREAKOUT
        assert reason == ReasonCode.RC_ENTRY_BREAKOUT_20D

    def test_only_one_entry_type_selected(self) -> None:
        breakout = EntrySetupResult(breakout_entry=True)
        pullback = EntrySetupResult(pullback_entry=True)
        entry_type, _ = resolve_entry_priority(
            breakout, pullback, Decimal("100"), Decimal("90")
        )
        assert entry_type != EntryType.PULLBACK
