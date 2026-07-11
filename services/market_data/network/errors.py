"""Hyperliquid network error types."""

from __future__ import annotations


class HyperliquidHttpError(Exception):
    """Base HTTP transport error."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class HyperliquidTimeoutError(HyperliquidHttpError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class HyperliquidConnectionError(HyperliquidHttpError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class HyperliquidRateLimitError(HyperliquidHttpError):
    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message, retryable=True)
        self.retry_after_seconds = retry_after_seconds


class HyperliquidHttpStatusError(HyperliquidHttpError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retryable: bool = False,
    ) -> None:
        super().__init__(message, retryable=retryable)
        self.status_code = status_code


class HyperliquidParseError(HyperliquidHttpError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class HyperliquidPaginationIncompleteError(HyperliquidParseError):
    """Historical pagination did not reach endTime — fail-closed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class HyperliquidWebSocketError(Exception):
    """WebSocket transport or protocol error."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class HyperliquidBufferOverflowError(HyperliquidWebSocketError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)
