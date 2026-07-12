"""Typed errors for market event bridge processing."""

from __future__ import annotations


class MarketEventProcessingError(Exception):
    """Base class for classified market event failures."""

    code: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RetryableContextNotReady(MarketEventProcessingError):
    """Transient missing context — event must remain retryable."""

    code = "RETRYABLE_CONTEXT_NOT_READY"


PERMANENT_CONFIGURATION_FAILURE = "PERMANENT_CONFIGURATION_FAILURE"
PERMANENT_CONFIGURATION_INVALID_TICK_SIZE = "PERMANENT_CONFIGURATION_INVALID_TICK_SIZE"
PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP = "PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP"
PERMANENT_CONFIGURATION_INVALID_MIN_QUANTITY = "PERMANENT_CONFIGURATION_INVALID_MIN_QUANTITY"
PERMANENT_CONFIGURATION_INVALID_MIN_NOTIONAL = "PERMANENT_CONFIGURATION_INVALID_MIN_NOTIONAL"
PERMANENT_CONFIGURATION_SYMBOL_MISMATCH = "PERMANENT_CONFIGURATION_SYMBOL_MISMATCH"
PERMANENT_CONFIGURATION_PRECISION_MISMATCH = "PERMANENT_CONFIGURATION_PRECISION_MISMATCH"

PERMANENT_CONFIGURATION_ERROR_CODES = frozenset(
    {
        PERMANENT_CONFIGURATION_FAILURE,
        PERMANENT_CONFIGURATION_INVALID_TICK_SIZE,
        PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP,
        PERMANENT_CONFIGURATION_INVALID_MIN_QUANTITY,
        PERMANENT_CONFIGURATION_INVALID_MIN_NOTIONAL,
        PERMANENT_CONFIGURATION_SYMBOL_MISMATCH,
        PERMANENT_CONFIGURATION_PRECISION_MISMATCH,
    }
)


def is_permanent_configuration_error(error: str | None) -> bool:
    if error is None:
        return False
    return error in PERMANENT_CONFIGURATION_ERROR_CODES


class PermanentConfigurationFailure(MarketEventProcessingError):
    """Permanent configuration or constraint failure — fail closed."""

    code = PERMANENT_CONFIGURATION_FAILURE

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        if error_code is not None:
            self.code = error_code


class FillNotDue(MarketEventProcessingError):
    """Entry fill subjob is not yet due — open processing remains deferred."""

    code = "FILL_NOT_DUE"

    def __init__(self, message: str = "entry fill not yet due") -> None:
        super().__init__(message)


class DailyEvaluationNotDue(MarketEventProcessingError):
    """Daily close evaluation is not yet due."""

    code = "DAILY_EVALUATION_NOT_DUE"

    def __init__(self, message: str = "daily evaluation not yet due") -> None:
        super().__init__(message)


class RetryableSchedulerDeferred(MarketEventProcessingError):
    """Scheduler returned a retryable SKIPPED outcome — event must remain retryable."""

    code = "RETRYABLE_SCHEDULER_DEFERRED"

    def __init__(self, message: str = "scheduler deferred") -> None:
        super().__init__(message)
