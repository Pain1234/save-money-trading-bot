"""Exchange rounding helpers — Risk Spec §2.1."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    """floor_to_step(x, step) = floor(x / step) × step."""
    if step <= 0:
        raise ValueError("step must be positive")
    steps = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return steps * step


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Long stop direction: floor to tick."""
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    steps = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return steps * tick_size
