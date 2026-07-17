"""Time-respecting block bootstrap helpers (P5-07 / #203).

Public infrastructure only — do not commit real research distributions to the
public tree. Prefer block bootstrap over IID daily-return shuffles.

Uses the Python standard library only (no hard numpy dependency).

Path bootstrap keeps each simulated series as a path so net-PnL and max
drawdown quantiles reflect path dependence (Accept rule: 5% net-PnL quantile).

Small samples must not produce false confidence: callers should treat
``ValueError`` from sample guards as documented N/A under the protocol.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapResult:
    """Legacy mean-of-path summary (kept for callers that only need means)."""

    n_simulations: int
    block_length: int
    seed: int
    quantiles: dict[str, float]
    mean: float


@dataclass(frozen=True)
class PathBootstrapResult:
    """Block-bootstrap path statistics for uncertainty analysis (#203)."""

    n_simulations: int
    block_length: int
    seed: int
    net_pnl_quantiles: dict[str, float]
    max_drawdown_quantiles: dict[str, float]
    mean_net_pnl: float
    mean_max_drawdown: float


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


def _qmap(values: list[float], quantiles: tuple[float, ...]) -> dict[str, float]:
    ordered = sorted(values)
    return {f"q{int(q * 100):02d}": _quantile(ordered, q) for q in quantiles}


def _validate_bootstrap_sample(values: Sequence[float], block_length: int) -> None:
    """Fail closed on samples that cannot support meaningful block bootstrap.

    Protocol: small-n → document N/A rather than emit false-confidence quantiles.
    """

    n = len(values)
    if n < 2:
        raise ValueError(
            "series too short for block bootstrap (need >= 2 points); "
            "document N/A rather than false confidence"
        )
    if block_length >= n:
        raise ValueError(
            "block_length must be < len(series) for meaningful block bootstrap; "
            "document N/A rather than false confidence"
        )


def _resample_path(
    values: Sequence[float],
    *,
    block_length: int,
    rng: random.Random,
) -> list[float]:
    n = len(values)
    n_blocks = math.ceil(n / block_length)
    max_start = max(n - block_length, 0)
    chunks: list[float] = []
    for _ in range(n_blocks):
        start = rng.randint(0, max_start) if max_start > 0 else 0
        chunks.extend(values[start : start + block_length])
    return chunks[:n]


def _path_net_pnl(period_returns: Sequence[float]) -> float:
    """Additive path PnL when ``period_returns`` are period PnL increments."""

    return float(sum(period_returns))


def _path_max_drawdown(period_returns: Sequence[float]) -> float:
    """Max drawdown of cumulative PnL path (≤ 0)."""

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in period_returns:
        equity += float(r)
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def block_bootstrap_paths(
    series: Sequence[float],
    *,
    block_length: int,
    n_simulations: int,
    seed: int,
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95),
) -> PathBootstrapResult:
    """Resample contiguous blocks into full paths; quantile path PnL and DD.

    ``series`` is a chronological sequence of period **net PnL increments**
    (same units as decision-rule net PnL). Each simulation keeps the path;
    reported ``net_pnl_quantiles`` are quantiles of path totals (not quantiles
    of the mean of IID draws). ``max_drawdown_quantiles`` use path dependence.

    Raises ``ValueError`` when the sample is too small for meaningful blocks
    (callers must record N/A instead of treating empty/trivial paths as evidence).
    """

    if block_length < 1:
        raise ValueError("block_length must be >= 1")
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")
    values = [float(x) for x in series]
    if not values:
        raise ValueError("series must be non-empty")
    _validate_bootstrap_sample(values, block_length)

    rng = random.Random(seed)
    net_pnls: list[float] = []
    max_dds: list[float] = []
    for _ in range(n_simulations):
        path = _resample_path(values, block_length=block_length, rng=rng)
        net_pnls.append(_path_net_pnl(path))
        max_dds.append(_path_max_drawdown(path))

    return PathBootstrapResult(
        n_simulations=n_simulations,
        block_length=block_length,
        seed=seed,
        net_pnl_quantiles=_qmap(net_pnls, quantiles),
        max_drawdown_quantiles=_qmap(max_dds, quantiles),
        mean_net_pnl=sum(net_pnls) / len(net_pnls),
        mean_max_drawdown=sum(max_dds) / len(max_dds),
    )


def block_bootstrap_means(
    series: Sequence[float],
    *,
    block_length: int,
    n_simulations: int,
    seed: int,
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95),
) -> BootstrapResult:
    """Quantiles of per-path arithmetic means (diagnostic only).

    For Accept-rule evidence use :func:`block_bootstrap_paths` (path net-PnL
    and drawdown quantiles). Mean-of-path alone does not satisfy #203.
    """

    if block_length < 1:
        raise ValueError("block_length must be >= 1")
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")
    values = [float(x) for x in series]
    if not values:
        raise ValueError("series must be non-empty")
    _validate_bootstrap_sample(values, block_length)

    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(n_simulations):
        sim = _resample_path(values, block_length=block_length, rng=rng)
        means.append(sum(sim) / n)
    return BootstrapResult(
        n_simulations=n_simulations,
        block_length=block_length,
        seed=seed,
        quantiles=_qmap(means, quantiles),
        mean=sum(means) / len(means),
    )
