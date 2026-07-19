"""Tests for benchmark calculation (#144 / #208)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from backtester.execution import (
    apply_entry_slippage,
    apply_exit_slippage,
    compute_fee,
    compute_funding_payment,
)
from backtester.models import FeeModel, FundingModel, HistoricalDataBundle, SlippageModel
from research.benchmark import (
    _buy_and_hold_net_return,
    compute_benchmark_result,
    compute_buy_and_hold_return,
)
from research.costs import cost_models_from_spec
from research.experiment_spec import parse_experiment_spec
from research.metrics_contract import BenchmarkRef
from strategy_engine.models import Candle, Timeframe

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def _daily(symbol: str, day: int, close: str) -> Candle:
    open_time = datetime(2024, 1, day, tzinfo=UTC)
    p = Decimal(close)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.DAILY,
        open_time=open_time,
        close_time=open_time.replace(hour=23, minute=59, second=59),
        open=p,
        high=p,
        low=p,
        close=p,
        volume=Decimal("1"),
        is_closed=True,
    )


def _btc_spec(**overrides: object):
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["symbols"] = ["BTC"]
    from research.symbol_constraints import hyperliquid_mainnet_v1_pins

    raw["symbol_constraints"] = hyperliquid_mainnet_v1_pins(("BTC",))
    raw.update(overrides)
    if "symbols" in overrides and "symbol_constraints" not in overrides:
        raw["symbol_constraints"] = hyperliquid_mainnet_v1_pins(
            tuple(str(s) for s in raw["symbols"])  # type: ignore[arg-type]
        )
    return parse_experiment_spec(raw)


def _bundle(*closes: str) -> HistoricalDataBundle:
    candles = tuple(_daily("BTC", i + 1, c) for i, c in enumerate(closes))
    return HistoricalDataBundle(
        daily={"BTC": candles},
        weekly={"BTC": ()},
        monthly={"BTC": ()},
    )


def test_buy_and_hold_return() -> None:
    assert compute_buy_and_hold_return(_bundle("100", "110"), "BTC") == Decimal("0.1")


def test_compute_benchmark_from_example_spec() -> None:
    ref, result = compute_benchmark_result(_btc_spec(), _bundle("100", "125"))
    assert "buy_and_hold" in ref.benchmark_id.lower()
    assert ref.gross_return == Decimal("0.25")
    assert ref.cost_parity is True
    assert ref.cost_model_version
    assert result < ref.gross_return
    assert result != Decimal("0.25")


def test_benchmark_net_reflects_higher_fees() -> None:
    low = _btc_spec()
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["symbols"] = ["BTC"]
    from research.symbol_constraints import hyperliquid_mainnet_v1_pins

    raw["symbol_constraints"] = hyperliquid_mainnet_v1_pins(("BTC",))
    raw["fee_assumption"] = {
        "entry_fee_rate": "0.05",
        "exit_fee_rate": "0.05",
        "model_version": "1.0",
    }
    high = parse_experiment_spec(raw)
    bundle = _bundle("100", "125")
    _, net_low = compute_benchmark_result(low, bundle)
    _, net_high = compute_benchmark_result(high, bundle)
    assert net_high < net_low


def test_exact_fee_component_reduces_net() -> None:
    """Entry+exit fees on fill notionals; shares sized at full starting_capital."""
    capital = Decimal("10000")
    first = Decimal("100")
    last = Decimal("110")
    fee = FeeModel(entry_fee_rate=Decimal("0.001"), exit_fee_rate=Decimal("0.001"))
    slip = SlippageModel(slippage_bps=Decimal("0"))
    funding = FundingModel(enabled=False, assumed_rate=None)
    entry_fill = apply_entry_slippage(first, slip)
    exit_fill = apply_exit_slippage(last, slip)
    shares = capital / entry_fill
    entry_fee = compute_fee(capital, fee.entry_fee_rate)
    exit_fee = compute_fee(shares * exit_fill, fee.exit_fee_rate)
    expected = (
        -entry_fee - exit_fee + shares * (exit_fill - entry_fill)
    ) / capital
    got = _buy_and_hold_net_return(
        starting_capital=capital,
        first_close=first,
        last_close=last,
        n_holding_days=1,
        fee=fee,
        slip=slip,
        funding=funding,
    )
    assert got == expected
    # Fee-first / shrink-shares would differ when fees are non-zero.
    shrink_shares = (capital - entry_fee) / entry_fill
    shrink_net = (
        -entry_fee
        - compute_fee(shrink_shares * exit_fill, fee.exit_fee_rate)
        + shrink_shares * (exit_fill - entry_fill)
    ) / capital
    assert got != shrink_net


def test_exact_slippage_uses_entry_fill_notional_for_funding() -> None:
    capital = Decimal("10000")
    first = Decimal("100")
    last = Decimal("100")
    fee = FeeModel(entry_fee_rate=Decimal("0"), exit_fee_rate=Decimal("0"))
    slip = SlippageModel(slippage_bps=Decimal("10"))  # 10 bps
    rate = Decimal("0.0001")
    funding = FundingModel(enabled=True, assumed_rate=rate)
    holding_days = 3
    entry_fill = apply_entry_slippage(first, slip)
    exit_fill = apply_exit_slippage(last, slip)
    shares = capital / entry_fill
    # Backtester funding notional = qty * entry_fill (not mid close).
    funding_cost = compute_funding_payment(capital, rate) * Decimal(holding_days)
    mid_notional_funding = (
        compute_funding_payment(shares * first, rate) * Decimal(holding_days)
    )
    assert funding_cost != mid_notional_funding
    assert funding_cost > mid_notional_funding  # mid notional understates funding
    end_equity = capital - funding_cost + shares * (exit_fill - entry_fill)
    expected = (end_equity - capital) / capital
    got = _buy_and_hold_net_return(
        starting_capital=capital,
        first_close=first,
        last_close=last,
        n_holding_days=holding_days,
        fee=fee,
        slip=slip,
        funding=funding,
    )
    assert got == expected


def test_holding_days_scale_funding_linearly() -> None:
    capital = Decimal("10000")
    fee = FeeModel(entry_fee_rate=Decimal("0"), exit_fee_rate=Decimal("0"))
    slip = SlippageModel(slippage_bps=Decimal("0"))
    funding = FundingModel(enabled=True, assumed_rate=Decimal("0.001"))
    one = _buy_and_hold_net_return(
        starting_capital=capital,
        first_close=Decimal("100"),
        last_close=Decimal("100"),
        n_holding_days=1,
        fee=fee,
        slip=slip,
        funding=funding,
    )
    two = _buy_and_hold_net_return(
        starting_capital=capital,
        first_close=Decimal("100"),
        last_close=Decimal("100"),
        n_holding_days=2,
        fee=fee,
        slip=slip,
        funding=funding,
    )
    assert one == Decimal("-0.001")
    assert two == Decimal("-0.002")


def test_cost_models_from_spec_wires_into_benchmark() -> None:
    spec = _btc_spec(
        fee_assumption={
            "entry_fee_rate": "0",
            "exit_fee_rate": "0",
            "model_version": "1.0",
        },
        slippage_assumption={"slippage_bps": "0", "model_version": "1.0"},
        funding_assumption={
            "enabled": True,
            "assumed_rate": "0.001",
            "model_version": "1.0",
        },
        starting_capital="10000",
    )
    fee, slip, funding = cost_models_from_spec(spec)
    assert fee.entry_fee_rate == Decimal("0")
    assert slip.slippage_bps == Decimal("0")
    assert funding.enabled is True
    # 3 candles → 2 holding days → net = -0.002
    _, net = compute_benchmark_result(spec, _bundle("100", "100", "100"))
    assert net == Decimal("-0.002")


def test_cost_parity_false_rejected_at_compute() -> None:
    ref = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_parity=False,
    )
    with pytest.raises(ValueError, match="cost_parity"):
        compute_benchmark_result(_btc_spec(), _bundle("100", "110"), ref=ref)


def test_unsupported_benchmark_fails() -> None:
    with pytest.raises(ValueError, match="unsupported benchmark"):
        compute_benchmark_result(
            _btc_spec(benchmark="sharpe_oracle"),
            _bundle("100", "110"),
        )
