"""Shared SymbolConstraints validation for production context and recovery."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

from risk_engine.models import SymbolConstraints

from paper_trading.market_event_errors import (
    PERMANENT_CONFIGURATION_FAILURE,
    PERMANENT_CONFIGURATION_INVALID_MIN_NOTIONAL,
    PERMANENT_CONFIGURATION_INVALID_MIN_QUANTITY,
    PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP,
    PERMANENT_CONFIGURATION_INVALID_TICK_SIZE,
    PERMANENT_CONFIGURATION_PRECISION_MISMATCH,
    PERMANENT_CONFIGURATION_SYMBOL_MISMATCH,
    PermanentConfigurationFailure,
)


def _decimal_is_finite(value: Decimal) -> bool:
    try:
        return math.isfinite(float(value))
    except (InvalidOperation, OverflowError, ValueError):
        return False


def _validate_positive_finite(
    *,
    field_name: str,
    value: Decimal,
    error_code: str,
    symbol: str,
) -> None:
    if not _decimal_is_finite(value):
        raise PermanentConfigurationFailure(
            f"invalid {field_name} for {symbol}: must be finite",
            error_code=error_code,
        )
    if value <= 0:
        raise PermanentConfigurationFailure(
            f"invalid {field_name} for {symbol}: must be > 0",
            error_code=error_code,
        )


def _validate_non_negative_finite(
    *,
    field_name: str,
    value: Decimal,
    error_code: str,
    symbol: str,
) -> None:
    if not _decimal_is_finite(value):
        raise PermanentConfigurationFailure(
            f"invalid {field_name} for {symbol}: must be finite",
            error_code=error_code,
        )
    if value < 0:
        raise PermanentConfigurationFailure(
            f"invalid {field_name} for {symbol}: must be >= 0",
            error_code=error_code,
        )


def _is_step_aligned(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return False
    quotient = value / step
    try:
        return quotient == quotient.to_integral_value()
    except (InvalidOperation, OverflowError, ValueError):
        return False


def validate_production_symbol_constraints(
    *,
    symbol: str,
    constraints: SymbolConstraints,
    expected_symbol: str | None = None,
) -> None:
    """Validate constraints with production fail-closed semantics."""
    if expected_symbol is not None and symbol != expected_symbol:
        raise PermanentConfigurationFailure(
            f"symbol mismatch: expected {expected_symbol}, got {symbol}",
            error_code=PERMANENT_CONFIGURATION_SYMBOL_MISMATCH,
        )

    _validate_positive_finite(
        field_name="price_tick_size",
        value=constraints.price_tick_size,
        error_code=PERMANENT_CONFIGURATION_INVALID_TICK_SIZE,
        symbol=symbol,
    )
    _validate_positive_finite(
        field_name="quantity_step",
        value=constraints.quantity_step,
        error_code=PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP,
        symbol=symbol,
    )
    _validate_positive_finite(
        field_name="minimum_quantity",
        value=constraints.minimum_quantity,
        error_code=PERMANENT_CONFIGURATION_INVALID_MIN_QUANTITY,
        symbol=symbol,
    )
    _validate_non_negative_finite(
        field_name="minimum_notional",
        value=constraints.minimum_notional,
        error_code=PERMANENT_CONFIGURATION_INVALID_MIN_NOTIONAL,
        symbol=symbol,
    )

    if constraints.minimum_quantity < constraints.quantity_step:
        raise PermanentConfigurationFailure(
            f"minimum_quantity below quantity_step for {symbol}",
            error_code=PERMANENT_CONFIGURATION_PRECISION_MISMATCH,
        )
    if not _is_step_aligned(constraints.minimum_quantity, constraints.quantity_step):
        raise PermanentConfigurationFailure(
            f"minimum_quantity not aligned to quantity_step for {symbol}",
            error_code=PERMANENT_CONFIGURATION_PRECISION_MISMATCH,
        )


def require_valid_production_constraints(
    *,
    symbol: str,
    constraints: SymbolConstraints | None,
) -> SymbolConstraints:
    if constraints is None:
        raise PermanentConfigurationFailure(
            f"missing symbol constraints for {symbol}",
            error_code=PERMANENT_CONFIGURATION_FAILURE,
        )
    validate_production_symbol_constraints(
        symbol=symbol,
        constraints=constraints,
        expected_symbol=symbol,
    )
    return constraints
