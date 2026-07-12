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


class PermanentConfigurationFailure(MarketEventProcessingError):
    """Permanent configuration or constraint failure — fail closed."""

    code = "PERMANENT_CONFIGURATION_FAILURE"


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
