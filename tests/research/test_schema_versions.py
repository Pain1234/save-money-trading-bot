"""Schema/cost version bumps and old/new compatibility (#169)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from research.costs import COST_MODEL_VERSION, SUPPORTED_COST_MODEL_VERSIONS
from research.metrics_contract import (
    METRICS_SCHEMA_VERSION,
    SUPPORTED_METRICS_SCHEMA_VERSIONS,
    BenchmarkRef,
    ResearchMetrics,
)


def _metrics(**overrides: object) -> ResearchMetrics:
    base = dict(
        schema_version=METRICS_SCHEMA_VERSION,
        start_capital=Decimal("100"),
        end_capital=Decimal("90"),
        gross_pnl=Decimal("0"),
        net_pnl=Decimal("-10"),
        fees=Decimal("2"),
        slippage_costs=Decimal("3"),
        funding_costs=Decimal("5"),
        funding_assumption="enabled:0.001",
        signal_count=0,
        order_count=0,
        fill_count=0,
        closed_trades=0,
        benchmark=BenchmarkRef(
            benchmark_id="buy_and_hold_BTC",
            benchmark_version="1.0",
            calculation="test",
            cost_model_version="1.1",
            gross_return=Decimal("0"),
        ),
        benchmark_result=Decimal("0"),
    )
    base.update(overrides)
    return ResearchMetrics(**base)  # type: ignore[arg-type]


def test_current_versions_bumped() -> None:
    assert METRICS_SCHEMA_VERSION == "1.2"
    assert COST_MODEL_VERSION == "1.1"
    assert "1.0" in SUPPORTED_METRICS_SCHEMA_VERSIONS
    assert "1.1" in SUPPORTED_METRICS_SCHEMA_VERSIONS
    assert "1.2" in SUPPORTED_METRICS_SCHEMA_VERSIONS
    assert "1.0" in SUPPORTED_COST_MODEL_VERSIONS
    assert "1.1" in SUPPORTED_COST_MODEL_VERSIONS


def test_schema_1_1_enforces_gross_identity() -> None:
    m = _metrics()
    assert m.schema_version == "1.2"
    with pytest.raises(ValueError, match="gross_pnl must equal"):
        _metrics(gross_pnl=Decimal("1"))


def test_legacy_schema_1_0_readable_without_identity_enforcement() -> None:
    # 1.0 may omit strict funding gross identity (pre-#169 contract).
    m = _metrics(
        schema_version="1.0",
        gross_pnl=Decimal("999"),  # intentionally wrong vs identity
        funding_costs=Decimal("0"),
    )
    assert m.schema_version == "1.0"


def test_unsupported_schema_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported metrics schema_version"):
        _metrics(schema_version="9.9")
