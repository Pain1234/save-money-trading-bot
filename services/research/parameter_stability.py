"""Small parameter neighborhood diagnostics (P5-06 / #202).

Perturbations are diagnostic only. Successful neighbors must not replace a
failed frozen candidate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def symmetric_neighborhood(
    frozen: dict[str, Any],
    *,
    int_deltas: dict[str, tuple[int, ...]] | None = None,
    decimal_relative_steps: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """Return frozen params plus one-at-a-time symmetric neighbors.

    Default deltas are intentionally small (protocol may override).
    """

    int_deltas = int_deltas or {
        "daily_ema_period": (-2, 2),
        "breakout_lookback": (-2, 2),
        "atr_period": (-2, 2),
    }
    decimal_relative_steps = decimal_relative_steps or {
        "stop_initial_atr_mult": ("-0.1", "0.1"),
        "trail_atr_mult": ("-0.1", "0.1"),
        "pullback_ema_tolerance": ("-0.001", "0.001"),
    }

    variants: list[dict[str, Any]] = [dict(frozen)]
    for key, deltas in int_deltas.items():
        if key not in frozen:
            continue
        base = int(frozen[key])
        for d in deltas:
            row = dict(frozen)
            row[key] = base + int(d)
            variants.append(row)
    for key, steps in decimal_relative_steps.items():
        if key not in frozen:
            continue
        base = Decimal(str(frozen[key]))
        for step in steps:
            row = dict(frozen)
            row[key] = str(base + Decimal(step))
            variants.append(row)
    return variants
