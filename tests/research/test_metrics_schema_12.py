"""Metrics schema 1.2 benchmark net semantics (#208 / Codex F1-F2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from research.metrics_contract import (
    METRICS_SCHEMA_VERSION,
    BenchmarkRef,
    ResearchMetrics,
)


def _base_kwargs(**overrides):
    bench = overrides.pop(
        "benchmark",
        BenchmarkRef(
            benchmark_id="buy_and_hold_BTC",
            benchmark_version="1.0",
            calculation="test",
            cost_model_version="1.1",
            gross_return=Decimal("0.25"),
        ),
    )
    data = dict(
        schema_version=METRICS_SCHEMA_VERSION,
        status="complete",
        start_capital=Decimal("10000"),
        end_capital=Decimal("11000"),
        gross_pnl=Decimal("1000"),
        net_pnl=Decimal("900"),
        fees=Decimal("50"),
        slippage_costs=Decimal("30"),
        funding_costs=Decimal("20"),
        funding_assumption="assumed_rate",
        signal_count=1,
        order_count=1,
        fill_count=1,
        closed_trades=1,
        benchmark=bench,
        benchmark_result=Decimal("0.20"),
    )
    data.update(overrides)
    return data


def test_schema_version_is_12() -> None:
    assert METRICS_SCHEMA_VERSION == "1.2"


def test_complete_1_2_requires_cost_model_version() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="",
        gross_return=Decimal("0.25"),
    )
    with pytest.raises(ValidationError, match="cost_model_version"):
        ResearchMetrics(**_base_kwargs(benchmark=bench))


def test_complete_1_2_requires_gross_return() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="1.1",
        gross_return=None,
    )
    with pytest.raises(ValidationError, match="gross_return"):
        ResearchMetrics(**_base_kwargs(benchmark=bench))


def test_complete_1_2_requires_benchmark_result() -> None:
    with pytest.raises(ValidationError, match="benchmark_result"):
        ResearchMetrics(**_base_kwargs(benchmark_result=None))


def test_legacy_1_1_allows_missing_gross_return() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="",
        gross_return=None,
    )
    # 1.1 gross identity: gross = net + fees + slip + funding
    m = ResearchMetrics(
        **_base_kwargs(
            schema_version="1.1",
            benchmark=bench,
            gross_pnl=Decimal("1000"),
            net_pnl=Decimal("900"),
            fees=Decimal("50"),
            slippage_costs=Decimal("30"),
            funding_costs=Decimal("20"),
        )
    )
    assert m.schema_version == "1.1"
    assert m.benchmark.gross_return is None


def test_legacy_1_1_complete_without_benchmark_result_still_loads() -> None:
    """1.1 complete payloads may omit benchmark_result (pre-1.2 contract)."""
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
    )
    m = ResearchMetrics(
        **_base_kwargs(
            schema_version="1.1",
            benchmark=bench,
            benchmark_result=None,
            gross_pnl=Decimal("1000"),
            net_pnl=Decimal("900"),
            fees=Decimal("50"),
            slippage_costs=Decimal("30"),
            funding_costs=Decimal("20"),
        )
    )
    assert m.benchmark_result is None


def test_complete_1_2_rejects_unknown_cost_model_version() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="9.9",
        gross_return=Decimal("0.25"),
    )
    with pytest.raises(ValidationError, match="not supported"):
        ResearchMetrics(**_base_kwargs(benchmark=bench))


def test_complete_1_2_rejects_cost_parity_false() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="1.1",
        gross_return=Decimal("0.25"),
        cost_parity=False,
    )
    with pytest.raises(ValidationError, match="cost_parity"):
        ResearchMetrics(**_base_kwargs(benchmark=bench))


def test_complete_1_2_rejects_period_parity_false() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="1.1",
        gross_return=Decimal("0.25"),
        period_parity=False,
    )
    with pytest.raises(ValidationError, match="period_parity"):
        ResearchMetrics(**_base_kwargs(benchmark=bench))


def test_complete_1_2_rejects_dataset_parity_false() -> None:
    bench = BenchmarkRef(
        benchmark_id="buy_and_hold_BTC",
        benchmark_version="1.0",
        calculation="test",
        cost_model_version="1.1",
        gross_return=Decimal("0.25"),
        dataset_parity=False,
    )
    with pytest.raises(ValidationError, match="dataset_parity"):
        ResearchMetrics(**_base_kwargs(benchmark=bench))
