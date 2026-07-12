"""Shared constraint acceptance matrix across production entry points."""

from __future__ import annotations

from decimal import Decimal

import pytest
from paper_trading.constraint_validation import validate_production_symbol_constraints
from paper_trading.execution import MissingSymbolConstraintsError, validate_symbol_constraints
from paper_trading.market_event_errors import PermanentConfigurationFailure
from risk_engine.models import SymbolConstraints
from risk_engine.validation import validate_constraints

from tests.paper_trading.conftest_execution import DEFAULT_CONSTRAINTS


def _constraints(**overrides: Decimal) -> SymbolConstraints:
    payload = DEFAULT_CONSTRAINTS.model_dump()
    payload.update(overrides)
    return SymbolConstraints.model_construct(**payload)


MATRIX_CASES: list[tuple[str, SymbolConstraints, bool]] = [
    ("valid", DEFAULT_CONSTRAINTS, True),
    ("tick_size_zero", _constraints(price_tick_size=Decimal("0")), False),
    ("tick_size_negative", _constraints(price_tick_size=Decimal("-0.01")), False),
    ("tick_size_nan", _constraints(price_tick_size=Decimal("NaN")), False),
    ("tick_size_infinity", _constraints(price_tick_size=Decimal("Infinity")), False),
    ("quantity_step_zero", _constraints(quantity_step=Decimal("0")), False),
    ("quantity_step_negative", _constraints(quantity_step=Decimal("-0.001")), False),
    ("quantity_step_nan", _constraints(quantity_step=Decimal("NaN")), False),
    ("quantity_step_infinity", _constraints(quantity_step=Decimal("Infinity")), False),
    ("minimum_quantity_below_step", _constraints(minimum_quantity=Decimal("0.0001")), False),
    ("minimum_quantity_not_step_aligned", _constraints(minimum_quantity=Decimal("0.0015")), False),
    ("minimum_quantity_zero", _constraints(minimum_quantity=Decimal("0")), False),
    ("minimum_quantity_negative", _constraints(minimum_quantity=Decimal("-1")), False),
    ("minimum_quantity_nan", _constraints(minimum_quantity=Decimal("NaN")), False),
    ("minimum_quantity_infinity", _constraints(minimum_quantity=Decimal("Infinity")), False),
    ("minimum_notional_negative", _constraints(minimum_notional=Decimal("-1")), False),
    ("minimum_notional_nan", _constraints(minimum_notional=Decimal("NaN")), False),
    ("minimum_notional_infinity", _constraints(minimum_notional=Decimal("Infinity")), False),
    ("minimum_notional_zero", _constraints(minimum_notional=Decimal("0")), True),
]


@pytest.mark.parametrize(("case_name", "constraints", "accepted"), MATRIX_CASES)
def test_constraint_matrix_context_builder(
    case_name: str,
    constraints: SymbolConstraints,
    accepted: bool,
) -> None:
    del case_name
    if accepted:
        validate_production_symbol_constraints(symbol="BTC", constraints=constraints)
        return
    with pytest.raises(PermanentConfigurationFailure):
        validate_production_symbol_constraints(symbol="BTC", constraints=constraints)


@pytest.mark.parametrize(("case_name", "constraints", "accepted"), MATRIX_CASES)
def test_constraint_matrix_risk_engine(
    case_name: str,
    constraints: SymbolConstraints,
    accepted: bool,
) -> None:
    del case_name
    error = validate_constraints(constraints)
    if accepted:
        assert error is None
    else:
        assert error is not None


@pytest.mark.parametrize(("case_name", "constraints", "accepted"), MATRIX_CASES)
def test_constraint_matrix_execution(
    case_name: str,
    constraints: SymbolConstraints,
    accepted: bool,
) -> None:
    del case_name
    if accepted:
        assert validate_symbol_constraints(constraints) is constraints
        return
    with pytest.raises(MissingSymbolConstraintsError):
        validate_symbol_constraints(constraints)
