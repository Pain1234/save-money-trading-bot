"""Time-respecting block bootstrap helpers (P5-07 / #203).

Public infrastructure only — do not commit real research distributions to the
public tree. Prefer block bootstrap over IID daily-return shuffles.

Uses the Python standard library only (no hard numpy dependency).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapResult:
    n_simulations: int
    block_length: int
    seed: int
    quantiles: dict[str, float]
    mean: float


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    pos = (len(sorted_vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    weight = pos - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def block_bootstrap_means(
    series: Sequence[float],
    *,
    block_length: int,
    n_simulations: int,
    seed: int,
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95),
) -> BootstrapResult:
    """Resample contiguous blocks and compute the mean of each path."""

    if block_length < 1:
        raise ValueError("block_length must be >= 1")
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")
    values = [float(x) for x in series]
    if not values:
        raise ValueError("series must be non-empty")

    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    n_blocks = math.ceil(n / block_length)
    max_start = max(n - block_length, 0)
    for _ in range(n_simulations):
        chunks: list[float] = []
        for _ in range(n_blocks):
            start = rng.randint(0, max_start) if max_start > 0 else 0
            chunks.extend(values[start : start + block_length])
        path = chunks[:n]
        means.append(sum(path) / n)

    ordered = sorted(means)
    qmap = {f"q{int(q * 100):02d}": _quantile(ordered, q) for q in quantiles}
    return BootstrapResult(
        n_simulations=n_simulations,
        block_length=block_length,
        seed=seed,
        quantiles=qmap,
        mean=sum(means) / len(means),
    )
