"""Technical indicators — Strategy Spec §4."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from strategy_engine.models import Candle


def compute_ema(closes: Sequence[Decimal], period: int) -> list[Decimal | None]:
    """
    EMA per Strategy Spec §4.1.

    EMA_n[0] = SMA_n of first n closes (at index period-1).
    EMA_n[t] = α(n) × C[t] + (1 − α(n)) × EMA_n[t−1]
    """
    if period <= 0:
        raise ValueError("period must be positive")

    n = len(closes)
    result: list[Decimal | None] = [None] * n
    if n < period:
        return result

    alpha = Decimal(2) / Decimal(period + 1)
    seed = sum(closes[:period]) / Decimal(period)
    result[period - 1] = seed

    prev = seed
    for i in range(period, n):
        prev = alpha * closes[i] + (Decimal(1) - alpha) * prev
        result[i] = prev

    return result


def compute_true_range(candles: Sequence[Candle]) -> list[Decimal | None]:
    """True Range; TR[0] undefined (no prior close)."""
    n = len(candles)
    tr: list[Decimal | None] = [None] * n
    for i in range(1, n):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr[i] = max(high - low, abs(high - prev_close), abs(low - prev_close))
    return tr


def compute_wilder_atr(candles: Sequence[Candle], period: int = 14) -> list[Decimal | None]:
    """
    Wilder ATR per Strategy Spec §4.2.

    ATR seed = SMA(TR, period) over indices 1..period.
    ATR[t] = (ATR[t−1] × (period−1) + TR[t]) / period
    """
    tr = compute_true_range(candles)
    n = len(candles)
    result: list[Decimal | None] = [None] * n

    if n <= period:
        return result

    seed_values: list[Decimal] = []
    for i in range(1, period + 1):
        val = tr[i]
        if val is None:
            return result
        seed_values.append(val)

    atr = sum(seed_values, Decimal(0)) / Decimal(period)
    result[period] = atr

    p_minus_1 = Decimal(period - 1)
    p = Decimal(period)
    for i in range(period + 1, n):
        tr_i = tr[i]
        if tr_i is None or atr is None:
            continue
        atr = (atr * p_minus_1 + tr_i) / p
        result[i] = atr

    return result


def compute_volume_sma(volumes: Sequence[Decimal], period: int) -> list[Decimal | None]:
    """Volume SMA: mean of V[t-period+1..t] inclusive."""
    n = len(volumes)
    result: list[Decimal | None] = [None] * n
    if n < period:
        return result

    p = Decimal(period)
    for i in range(period - 1, n):
        window = volumes[i - period + 1 : i + 1]
        result[i] = sum(window, Decimal(0)) / p

    return result


def compute_volume_ratio(volumes: Sequence[Decimal], period: int = 20) -> list[Decimal | None]:
    """
    Volume Ratio per Strategy Spec §4.3.

    VolSMA20[t] = (1/period) × Σ(i=t−19..t) V[i]
    VolumeRatio[t] = V[t] / VolSMA20[t]
    """
    sma = compute_volume_sma(volumes, period)
    result: list[Decimal | None] = [None] * len(volumes)
    for i, denom in enumerate(sma):
        if denom is None or denom == 0:
            result[i] = None
        else:
            result[i] = volumes[i] / denom
    return result


def compute_high20(highs: Sequence[Decimal], lookback: int = 20) -> list[Decimal | None]:
    """
    20-day high for breakout — Strategy Spec §4.4.

    High20[t] = max(H[t−1], …, H[t−lookback]).
    Current candle t is NOT included.
    """
    n = len(highs)
    result: list[Decimal | None] = [None] * n
    for t in range(lookback, n):
        window = highs[t - lookback : t]
        result[t] = max(window)
    return result


def compute_highest_close_since_entry(
    closes: Sequence[Decimal],
    entry_index: int,
    end_index: int,
) -> Decimal:
    """Highest daily close from entry_index through end_index inclusive."""
    if entry_index < 0 or end_index >= len(closes) or entry_index > end_index:
        raise ValueError("Invalid index range for highest close")
    return max(closes[entry_index : end_index + 1])
