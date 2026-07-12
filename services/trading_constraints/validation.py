"""Canonical SymbolConstraints validation for all production entry points."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from risk_engine.models import SymbolConstraints

INVALID_TICK_SIZE = "INVALID_TICK_SIZE"
INVALID_QUANTITY_STEP = "INVALID_QUANTITY_STEP"
INVALID_MIN_QUANTITY = "INVALID_MIN_QUANTITY"
INVALID_MIN_NOTIONAL = "INVALID_MIN_NOTIONAL"
PRECISION_MISMATCH = "PRECISION_MISMATCH"


@dataclass(frozen=True)
class ConstraintValidationError:
    field: str
    code: str
    message: str


def _decimal_is_finite(value: Decimal) -> bool:
    try:
        return math.isfinite(float(value))
    except (InvalidOperation, OverflowError, ValueError):
        return False


def _is_step_aligned(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return False
    quotient = value / step
    try:
        return quotient == quotient.to_integral_value()
    except (InvalidOperation, OverflowError, ValueError):
        return False


def validate_symbol_constraints_core(
    constraints: SymbolConstraints,
) -> ConstraintValidationError | None:
    """Return the first constraint violation, or None when constraints are valid."""
    positive_fields = (
        ("price_tick_size", constraints.price_tick_size, INVALID_TICK_SIZE),
        ("quantity_step", constraints.quantity_step, INVALID_QUANTITY_STEP),
        ("minimum_quantity", constraints.minimum_quantity, INVALID_MIN_QUANTITY),
    )
    for field_name, value, code in positive_fields:
        if not _decimal_is_finite(value):
            return ConstraintValidationError(
                field=field_name,
                code=code,
                message=f"{field_name} must be finite",
            )
        if value <= 0:
            return ConstraintValidationError(
                field=field_name,
                code=code,
                message=f"{field_name} must be > 0",
            )

    min_notional = constraints.minimum_notional
    if not _decimal_is_finite(min_notional):
        return ConstraintValidationError(
            field="minimum_notional",
            code=INVALID_MIN_NOTIONAL,
            message="minimum_notional must be finite",
        )
    if min_notional < 0:
        return ConstraintValidationError(
            field="minimum_notional",
            code=INVALID_MIN_NOTIONAL,
            message="minimum_notional must be >= 0",
        )

    step = constraints.quantity_step
    min_qty = constraints.minimum_quantity
    if min_qty < step:
        return ConstraintValidationError(
            field="minimum_quantity",
            code=PRECISION_MISMATCH,
            message="minimum_quantity below quantity_step",
        )
    if not _is_step_aligned(min_qty, step):
        return ConstraintValidationError(
            field="minimum_quantity",
            code=PRECISION_MISMATCH,
            message="minimum_quantity not aligned to quantity_step",
        )
    return None
