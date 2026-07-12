"""Regression tests for ProductionContextBuilder readiness wiring."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from paper_trading.clock import FixedClock
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperExecutionConfig
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.symbol_constraints import StaticSymbolConstraintsProvider
from risk_engine.models import RiskParameters

from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.integration.lifecycle_helpers import btc_eth_sol_constraints


def _builder(*, market_data_ready):
    repo = MagicMock()
    runtime = MagicMock()
    runtime.status = RuntimeStatus.READY
    runtime.kill_switch = False
    runtime.paused = False
    repo.get_runtime_state.return_value = runtime

    bundle = MagicMock()
    bundle.is_usable = True
    market_data = MagicMock()
    market_data.build_strategy_bundle.return_value = bundle

    config = MagicMock()
    config.symbols = ("BTC",)

    execution_config = PaperExecutionConfig(
        fee_rate=Decimal("0.0005"),
        slippage_bps=Decimal("5"),
        max_leverage=Decimal("2"),
    )
    risk_params = RiskParameters(
        risk_per_trade_pct=Decimal("0.005"),
        max_portfolio_risk_pct=Decimal("0.02"),
        max_leverage=Decimal("2"),
    )

    return (
        ProductionContextBuilder(
            market_data=market_data,
            repository=repo,
            config=config,
            constraints=StaticSymbolConstraintsProvider(btc_eth_sol_constraints()),
            clock=FixedClock(utc_dt(2024, 6, 1)),
            execution_config=execution_config,
            risk_params=risk_params,
            market_data_ready=market_data_ready,
        ),
        utc_dt(2024, 6, 1),
    )


def test_production_context_builder_requires_market_data_ready_source() -> None:
    repo = MagicMock()
    config = MagicMock()
    with pytest.raises(ValueError, match="market_data_ready source is required"):
        ProductionContextBuilder(
            market_data=MagicMock(),
            repository=repo,
            config=config,
            constraints=StaticSymbolConstraintsProvider(btc_eth_sol_constraints()),
            clock=FixedClock(utc_dt(2024, 1, 1)),
            execution_config=PaperExecutionConfig(
                fee_rate=Decimal("0.0005"),
                slippage_bps=Decimal("5"),
                max_leverage=Decimal("2"),
            ),
        )


def test_runtime_false_blocks_market_data_ready_gate() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: False)
    context = builder.build_evaluation_context("BTC", eval_time)
    assert context is not None
    entry_gates = context["symbols"]["BTC"]["entry_gates"]
    assert entry_gates.market_data_ready is False


def test_runtime_true_allows_existing_evaluation_path() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: True)
    context = builder.build_evaluation_context("BTC", eval_time)
    assert context is not None
    entry_gates = context["symbols"]["BTC"]["entry_gates"]
    assert entry_gates.market_data_ready is True


def test_stub_boolean_readiness_is_supported_via_lambda() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: True)
    assert builder.build_evaluation_context("BTC", eval_time) is not None
