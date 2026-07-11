"""Daily entry setups — Strategy Spec §5.4–§5.6."""

from __future__ import annotations

from decimal import Decimal

from strategy_engine.models import (
    EntrySetupResult,
    EntryType,
    PullbackConditions,
    ReasonCode,
    RegimeResult,
    StrategyParameters,
    TrendResult,
)


def evaluate_volume_ok(
    volume_ratio: Decimal | None,
    volume_ratio_min: Decimal,
) -> bool:
    """VolumeOK[t] = VolumeRatio[t] >= volume_ratio_min."""
    if volume_ratio is None:
        return False
    return volume_ratio >= volume_ratio_min


def evaluate_breakout_setup(
    close_t: Decimal,
    high20: Decimal | None,
    ema20_daily: Decimal | None,
    regime: RegimeResult,
    trend: TrendResult,
    volume_ok: bool,
) -> EntrySetupResult:
    """BreakoutEntry per Strategy Spec §5.4."""
    price_cond = high20 is not None and close_t > high20
    above_ema = ema20_daily is not None and close_t > ema20_daily

    breakout_entry = (
        price_cond
        and above_ema
        and regime.regime_long
        and trend.trend_confirmed
        and volume_ok
    )

    return EntrySetupResult(
        breakout_entry=breakout_entry,
        breakout_price_condition=price_cond,
        close_above_ema20=above_ema,
        volume_ok=volume_ok,
        high20=high20,
    )


def evaluate_pullback_setup(
    close_t: Decimal,
    low_t: Decimal,
    close_prev: Decimal | None,
    ema20_daily: Decimal | None,
    ema20_daily_prev: Decimal | None,
    regime: RegimeResult,
    trend: TrendResult,
    volume_ok: bool,
    params: StrategyParameters,
) -> EntrySetupResult:
    """PullbackEntry P1–P6 per Strategy Spec §5.5."""
    if ema20_daily is None:
        return EntrySetupResult(
            pullback_conditions=PullbackConditions(),
            volume_ok=volume_ok,
        )

    ema_touch_upper = ema20_daily * (Decimal(1) + params.pullback_ema_tolerance)

    p1 = close_t > ema20_daily
    p2 = low_t <= ema_touch_upper
    p3 = (
        close_prev is not None
        and ema20_daily_prev is not None
        and close_prev > ema20_daily_prev
    )
    p4 = regime.regime_long
    p5 = trend.trend_confirmed
    p6 = volume_ok

    conditions = PullbackConditions(
        p1_close_above_ema=p1,
        p2_low_touches_ema=p2,
        p3_prior_close_above_ema=p3,
        p4_regime_long=p4,
        p5_trend_confirmed=p5,
        p6_volume_ok=p6,
    )

    pullback_entry = p1 and p2 and p3 and p4 and p5 and p6

    return EntrySetupResult(
        pullback_entry=pullback_entry,
        close_above_ema20=p1,
        volume_ok=volume_ok,
        ema_touch_upper=ema_touch_upper,
        pullback_conditions=conditions,
    )


def resolve_entry_priority(
    breakout: EntrySetupResult,
    pullback: EntrySetupResult,
    entry_price: Decimal,
    stop_initial: Decimal | None,
) -> tuple[EntryType | None, ReasonCode | None]:
    """
    Signal priority — Strategy Spec §5.6.

    If both breakout and pullback: single intent with entry_type=BREAKOUT.
    """
    if breakout.breakout_entry:
        return EntryType.BREAKOUT, ReasonCode.RC_ENTRY_BREAKOUT_20D
    if pullback.pullback_entry:
        return EntryType.PULLBACK, ReasonCode.RC_ENTRY_PULLBACK_EMA20
    return None, None
