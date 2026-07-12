"""Shared SymbolConstraints validation for production context and recovery."""

from __future__ import annotations

from risk_engine.models import SymbolConstraints
from trading_constraints.validation import (
    INVALID_MIN_NOTIONAL,
    INVALID_MIN_QUANTITY,
    INVALID_QUANTITY_STEP,
    INVALID_TICK_SIZE,
    PRECISION_MISMATCH,
    validate_symbol_constraints_core,
)

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

_PRODUCTION_ERROR_CODES = {
    INVALID_TICK_SIZE: PERMANENT_CONFIGURATION_INVALID_TICK_SIZE,
    INVALID_QUANTITY_STEP: PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP,
    INVALID_MIN_QUANTITY: PERMANENT_CONFIGURATION_INVALID_MIN_QUANTITY,
    INVALID_MIN_NOTIONAL: PERMANENT_CONFIGURATION_INVALID_MIN_NOTIONAL,
    PRECISION_MISMATCH: PERMANENT_CONFIGURATION_PRECISION_MISMATCH,
}


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

    violation = validate_symbol_constraints_core(constraints)
    if violation is None:
        return
    raise PermanentConfigurationFailure(
        f"invalid {violation.field} for {symbol}: {violation.message}",
        error_code=_PRODUCTION_ERROR_CODES.get(
            violation.code,
            PERMANENT_CONFIGURATION_FAILURE,
        ),
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
