"""Benchmark calculation for research metrics (Issue #144)."""

from __future__ import annotations

import re
from decimal import Decimal

from backtester.models import HistoricalDataBundle

from research.experiment_spec import ExperimentSpec
from research.metrics_contract import BenchmarkRef, parse_benchmark_ref

_BUY_HOLD = re.compile(r"^buy_and_hold_([A-Za-z0-9]+)(?:@.+)?$", re.IGNORECASE)


def resolve_benchmark_ref(spec: ExperimentSpec) -> BenchmarkRef:
    """Parse Spec.benchmark and require non-empty id/version."""
    ref = parse_benchmark_ref(spec.benchmark)
    if not ref.benchmark_id.strip() or not ref.benchmark_version.strip():
        msg = "benchmark_id/version missing; report remains incomplete/invalid"
        raise ValueError(msg)
    return ref


def compute_buy_and_hold_return(
    bundle: HistoricalDataBundle,
    symbol: str,
) -> Decimal:
    """Net return of buy-and-hold from first to last closed daily candle."""
    dailies = bundle.daily.get(symbol)
    if not dailies:
        msg = f"benchmark dataset parity failed: no daily candles for {symbol}"
        raise ValueError(msg)
    closed = [c for c in dailies if c.is_closed]
    if len(closed) < 2:
        msg = f"benchmark period parity failed: need >=2 closed candles for {symbol}"
        raise ValueError(msg)
    first = closed[0].close
    last = closed[-1].close
    if first <= 0:
        msg = "benchmark calculation failed: non-positive first close"
        raise ValueError(msg)
    return (last - first) / first


def compute_benchmark_result(
    spec: ExperimentSpec,
    bundle: HistoricalDataBundle,
    *,
    ref: BenchmarkRef | None = None,
) -> tuple[BenchmarkRef, Decimal]:
    """Compute benchmark_result with fail-closed parity checks.

    Supported: ``buy_and_hold_<SYMBOL>`` (optional ``@version``).
    Buy-and-hold uses zero trading costs by definition; ``cost_parity`` means
    that assumption is declared explicitly on the BenchmarkRef.
    """
    resolved = ref or resolve_benchmark_ref(spec)
    match = _BUY_HOLD.match(resolved.benchmark_id)
    if match is None:
        # Also accept id like buy_and_hold_BTC when parse_benchmark_ref kept full string
        match = _BUY_HOLD.match(spec.benchmark.split("@", 1)[0].strip())
    if match is None:
        msg = (
            f"unsupported benchmark_id {resolved.benchmark_id!r}; "
            "expected buy_and_hold_<SYMBOL>"
        )
        raise ValueError(msg)
    symbol = match.group(1).upper()
    # Dataset parity: symbol must be in experiment symbols and bundle
    exp_symbols = {s.value for s in spec.symbols}
    if symbol not in exp_symbols:
        msg = (
            f"benchmark dataset parity failed: {symbol} not in experiment symbols"
        )
        raise ValueError(msg)
    if not resolved.period_parity or not resolved.dataset_parity:
        msg = "benchmark period/dataset parity flags must be true for P4 runs"
        raise ValueError(msg)
    if not resolved.cost_parity:
        msg = (
            "benchmark cost_parity must be true "
            "(buy-and-hold declares zero-fee cost model)"
        )
        raise ValueError(msg)
    result = compute_buy_and_hold_return(bundle, symbol)
    enriched = BenchmarkRef(
        benchmark_id=resolved.benchmark_id
        if resolved.benchmark_id.lower().startswith("buy_and_hold_")
        else f"buy_and_hold_{symbol}",
        benchmark_version=resolved.benchmark_version,
        calculation=(
            f"buy_and_hold {symbol}: (last_close-first_close)/first_close "
            "over run dataset daily candles; zero trading costs"
        ),
        period_parity=True,
        dataset_parity=True,
        cost_parity=True,
    )
    return enriched, result
