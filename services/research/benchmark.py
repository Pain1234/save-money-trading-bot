"""Benchmark calculation for research metrics (Issue #144 / #208)."""

from __future__ import annotations

import re
from decimal import Decimal

from backtester.models import HistoricalDataBundle

from research.costs import COST_MODEL_VERSION, require_cost_fields
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
    """Gross price return of buy-and-hold from first to last closed daily candle."""
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


def _buy_and_hold_net_return(
    *,
    starting_capital: Decimal,
    first_close: Decimal,
    last_close: Decimal,
    n_holding_days: int,
    entry_fee_rate: Decimal,
    exit_fee_rate: Decimal,
    slippage_bps: Decimal,
    funding_enabled: bool,
    funding_assumed_rate: Decimal | None,
) -> Decimal:
    """Apply Spec cost assumptions to a single buy-and-hold round trip."""
    if starting_capital <= 0 or first_close <= 0:
        msg = "benchmark net calculation requires positive capital and first close"
        raise ValueError(msg)
    slip = slippage_bps / Decimal("10000")
    entry_px = first_close * (Decimal("1") + slip)
    entry_fee = starting_capital * entry_fee_rate
    investable = starting_capital - entry_fee
    if investable <= 0:
        msg = "benchmark net calculation failed: entry fee consumes capital"
        raise ValueError(msg)
    shares = investable / entry_px
    exit_px = last_close * (Decimal("1") - slip)
    proceeds = shares * exit_px
    exit_fee = proceeds * exit_fee_rate
    funding = Decimal("0")
    if funding_enabled:
        if funding_assumed_rate is None:
            msg = "funding assumed_rate required when funding enabled for benchmark"
            raise ValueError(msg)
        # One funding application per held daily candle after entry.
        funding = shares * first_close * funding_assumed_rate * Decimal(n_holding_days)
    net_end = proceeds - exit_fee - funding
    return (net_end - starting_capital) / starting_capital


def compute_benchmark_result(
    spec: ExperimentSpec,
    bundle: HistoricalDataBundle,
    *,
    ref: BenchmarkRef | None = None,
) -> tuple[BenchmarkRef, Decimal]:
    """Compute benchmark_result (net) with fail-closed parity checks.

    Supported: `buy_and_hold_<SYMBOL>` (optional `@version`).

    `cost_parity=True` means the Spec fee/slippage/funding model is applied
    to the benchmark (same cost assumptions as the experiment). Gross price
    return is recorded on `BenchmarkRef.gross_return`; the returned Decimal
    is the **net** return after those costs.
    """
    require_cost_fields(spec)
    resolved = ref or resolve_benchmark_ref(spec)
    match = _BUY_HOLD.match(resolved.benchmark_id)
    if match is None:
        match = _BUY_HOLD.match(spec.benchmark.split("@", 1)[0].strip())
    if match is None:
        msg = (
            f"unsupported benchmark_id {resolved.benchmark_id!r}; "
            "expected buy_and_hold_<SYMBOL>"
        )
        raise ValueError(msg)
    symbol = match.group(1).upper()
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
            "(apply Spec cost model to buy-and-hold)"
        )
        raise ValueError(msg)

    dailies = bundle.daily.get(symbol)
    if not dailies:
        msg = f"benchmark dataset parity failed: no daily candles for {symbol}"
        raise ValueError(msg)
    closed = [c for c in dailies if c.is_closed]
    if len(closed) < 2:
        msg = f"benchmark period parity failed: need >=2 closed candles for {symbol}"
        raise ValueError(msg)
    first_close = closed[0].close
    last_close = closed[-1].close
    gross = (last_close - first_close) / first_close
    holding_days = len(closed) - 1
    fee = spec.fee_assumption
    slip = spec.slippage_assumption
    funding = spec.funding_assumption
    assert fee.entry_fee_rate is not None and fee.exit_fee_rate is not None
    assert slip.slippage_bps is not None
    net = _buy_and_hold_net_return(
        starting_capital=spec.starting_capital,
        first_close=first_close,
        last_close=last_close,
        n_holding_days=holding_days,
        entry_fee_rate=fee.entry_fee_rate,
        exit_fee_rate=fee.exit_fee_rate,
        slippage_bps=slip.slippage_bps,
        funding_enabled=funding.enabled,
        funding_assumed_rate=funding.assumed_rate,
    )
    enriched = BenchmarkRef(
        benchmark_id=resolved.benchmark_id
        if resolved.benchmark_id.lower().startswith("buy_and_hold_")
        else f"buy_and_hold_{symbol}",
        benchmark_version=resolved.benchmark_version,
        calculation=(
            f"buy_and_hold {symbol}: gross=(last-first)/first; "
            f"net applies Spec fees/slippage/funding (cost_model={COST_MODEL_VERSION})"
        ),
        period_parity=True,
        dataset_parity=True,
        cost_parity=True,
        cost_model_version=COST_MODEL_VERSION,
        gross_return=gross,
    )
    return enriched, net
