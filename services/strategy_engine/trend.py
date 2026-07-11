"""Weekly trend filter — Strategy Spec §5.2, §8.4."""

from __future__ import annotations

from decimal import Decimal

from strategy_engine.models import ReasonCode, TrendResult


def evaluate_weekly_trend(
    ema20_weekly: Decimal | None,
    ema50_weekly: Decimal | None,
) -> TrendResult:
    """
    TrendConfirmed[t] = EMA20_week[t] > EMA50_week[t].

    Weekly trend break blocks new entries only; no auto-exit in V1.
    """
    if ema20_weekly is None or ema50_weekly is None:
        return TrendResult(
            trend_confirmed=False,
            ema20_weekly=ema20_weekly,
            ema50_weekly=ema50_weekly,
            reason_code=ReasonCode.RC_REJECT_WARMUP,
        )

    trend_confirmed = ema20_weekly > ema50_weekly
    return TrendResult(
        trend_confirmed=trend_confirmed,
        ema20_weekly=ema20_weekly,
        ema50_weekly=ema50_weekly,
        reason_code=None if trend_confirmed else ReasonCode.RC_REJECT_TREND,
    )
