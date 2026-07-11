"""Monthly regime filter — Strategy Spec §5.1."""

from __future__ import annotations

from decimal import Decimal

from strategy_engine.models import ReasonCode, RegimeResult


def evaluate_monthly_regime(
    monthly_close: Decimal | None,
    ema20_monthly: Decimal | None,
) -> RegimeResult:
    """
    RegimeLong[t] = C_month[t] > EMA20_month[t].
    """
    if monthly_close is None or ema20_monthly is None:
        return RegimeResult(
            regime_long=False,
            monthly_close=monthly_close,
            ema20_monthly=ema20_monthly,
            reason_code=ReasonCode.RC_REJECT_WARMUP,
        )

    regime_long = monthly_close > ema20_monthly
    return RegimeResult(
        regime_long=regime_long,
        monthly_close=monthly_close,
        ema20_monthly=ema20_monthly,
        reason_code=None if regime_long else ReasonCode.RC_REJECT_REGIME,
    )
