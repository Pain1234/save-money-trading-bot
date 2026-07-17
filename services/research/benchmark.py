"""Benchmark calculation for research metrics (Issue #144 / #208)."""

from __future__ import annotations

import re
from decimal import Decimal

from backtester.execution import (
    apply_entry_slippage,
    apply_exit_slippage,
    compute_fee,
    compute_funding_payment,
)
from backtester.models import FeeModel, FundingModel, HistoricalDataBundle, SlippageModel

from research.costs import COST_MODEL_VERSION, cost_models_from_spec, require_cost_fields
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
    fee: FeeModel,
    slip: SlippageModel,
    funding: FundingModel,
) -> Decimal:
    """Apply Spec cost models to a single buy-and-hold round trip.

    Capital / notional convention (futures-style, matches backtester):

    - Entry fill = ``apply_entry_slippage(first_close)``
    - Size ``shares`` so entry notional ``shares * entry_fill == starting_capital``
    - Entry fee = ``compute_fee(entry_notional, entry_fee_rate)`` charged separately
      (does **not** shrink share count)
    - Funding notional = ``shares * entry_fill`` (entry-fill notional), once per
      holding day (``n_holding_days = n_closed_candles - 1``)
    - Exit fill = ``apply_exit_slippage(last_close)``
    - Exit fee = ``compute_fee(shares * exit_fill, exit_fee_rate)``
    - ``net_return = (end_equity - starting_capital) / starting_capital``
    """
    if starting_capital <= 0 or first_close <= 0:
        msg = "benchmark net calculation requires positive capital and first close"
        raise ValueError(msg)
    if n_holding_days < 1:
        msg = "benchmark net calculation requires at least one holding day"
        raise ValueError(msg)

    entry_fill = apply_entry_slippage(first_close, slip)
    if entry_fill <= 0:
        msg = "benchmark net calculation failed: non-positive entry fill"
        raise ValueError(msg)

    entry_notional = starting_capital
    shares = entry_notional / entry_fill
    entry_fee = compute_fee(entry_notional, fee.entry_fee_rate)

    exit_fill = apply_exit_slippage(last_close, slip)
    exit_notional = shares * exit_fill
    exit_fee = compute_fee(exit_notional, fee.exit_fee_rate)

    funding_cost = Decimal("0")
    if funding.enabled:
        if funding.assumed_rate is None:
            msg = "funding assumed_rate required when funding enabled for benchmark"
            raise ValueError(msg)
        per_day = compute_funding_payment(entry_notional, funding.assumed_rate)
        funding_cost = per_day * Decimal(n_holding_days)

    # Mark-to-market on fills minus fees/funding (cash not reduced by notional).
    end_equity = (
        starting_capital
        - entry_fee
        - exit_fee
        - funding_cost
        + shares * (exit_fill - entry_fill)
    )
    return (end_equity - starting_capital) / starting_capital


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
    fee_model, slip_model, funding_model = cost_models_from_spec(spec)
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
    net = _buy_and_hold_net_return(
        starting_capital=spec.starting_capital,
        first_close=first_close,
        last_close=last_close,
        n_holding_days=holding_days,
        fee=fee_model,
        slip=slip_model,
        funding=funding_model,
    )
    enriched = BenchmarkRef(
        benchmark_id=resolved.benchmark_id
        if resolved.benchmark_id.lower().startswith("buy_and_hold_")
        else f"buy_and_hold_{symbol}",
        benchmark_version=resolved.benchmark_version,
        calculation=(
            f"buy_and_hold {symbol}: gross=(last-first)/first; "
            f"net applies Spec fees/slippage/funding via execution primitives "
            f"(cost_model={COST_MODEL_VERSION}; entry notional=starting_capital)"
        ),
        period_parity=True,
        dataset_parity=True,
        cost_parity=True,
        cost_model_version=COST_MODEL_VERSION,
        gross_return=gross,
    )
    return enriched, net
