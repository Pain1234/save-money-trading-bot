"""Tests for paper execution engine."""

from __future__ import annotations

from decimal import Decimal

import pytest
from paper_trading.execution import (
    EntryExecutionInput,
    MissingSymbolConstraintsError,
    PaperExecutionEngine,
    validate_symbol_constraints,
)
from risk_engine.models import RiskParameters
from strategy_engine.models import StrategyParameters

from tests.paper_trading.conftest_execution import (
    DEFAULT_CONSTRAINTS,
    EXECUTION_CONFIG,
    make_trade_intent,
    utc_dt,
)


def test_missing_constraints_fail_closed() -> None:
    with pytest.raises(MissingSymbolConstraintsError):
        validate_symbol_constraints(None)


def test_entry_execution_requires_valid_open() -> None:
    engine = PaperExecutionEngine()
    intent = make_trade_intent()
    result = engine.compute_entry_execution(
        EntryExecutionInput(
            intent=intent,
            open_ref=Decimal("0"),
            atr14=Decimal("1000"),
            candle_open_time=utc_dt(2024, 1, 16),
            constraints=DEFAULT_CONSTRAINTS,
            wallet_cash=Decimal("100000"),
            open_positions=(),
            pending_intents=(),
            pending_intent_ids=frozenset(),
            processed_intent_ids=frozenset(),
            day_candles={},
            prior_closes={},
            strategy_params=StrategyParameters(),
            risk_params=RiskParameters(),
            execution_config=EXECUTION_CONFIG,
        )
    )
    assert result.approved is False
