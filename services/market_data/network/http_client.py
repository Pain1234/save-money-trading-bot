"""Async HTTP client for Hyperliquid public /info endpoint."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from market_data.config import HyperliquidPublicConfig
from market_data.network.errors import (
    HyperliquidConnectionError,
    HyperliquidHttpStatusError,
    HyperliquidParseError,
    HyperliquidRateLimitError,
    HyperliquidTimeoutError,
)
from market_data.network.json_utils import loads_decimal
from market_data.network.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)

SleepFn = Callable[[float], Awaitable[None]]


async def default_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


class HyperliquidHttpClient:
    """Read-only Hyperliquid HTTP client with retries and Decimal-safe JSON."""

    def __init__(
        self,
        config: HyperliquidPublicConfig,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: SleepFn = default_sleep,
    ) -> None:
        self._config = config
        self._sleep = sleep
        self._limiter = AsyncRateLimiter(config.max_http_concurrency)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=config.http_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                config.request_timeout_seconds,
                connect=config.connect_timeout_seconds,
            ),
            headers={"User-Agent": config.user_agent, "Content-Type": "application/json"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def post_info(self, body: dict[str, Any], *, request_id: str | None = None) -> Any:
        async def _call() -> Any:
            async with self._limiter.acquire():
                try:
                    response = await self._client.post("/info", json=body)
                except httpx.TimeoutException as exc:
                    raise HyperliquidTimeoutError(str(exc)) from exc
                except httpx.RequestError as exc:
                    raise HyperliquidConnectionError(str(exc)) from exc

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else None
                    raise HyperliquidRateLimitError(
                        "HTTP 429 rate limited",
                        retry_after_seconds=delay,
                    )
                if 400 <= response.status_code < 500:
                    raise HyperliquidHttpStatusError(
                        f"HTTP {response.status_code}: {response.text}",
                        status_code=response.status_code,
                        retryable=False,
                    )
                if response.status_code >= 500:
                    raise HyperliquidHttpStatusError(
                        f"HTTP {response.status_code}: {response.text}",
                        status_code=response.status_code,
                        retryable=True,
                    )
                if not response.content:
                    raise HyperliquidParseError("Empty HTTP response body")
                try:
                    return loads_decimal(response.text)
                except (ValueError, TypeError) as exc:
                    raise HyperliquidParseError(f"Invalid JSON: {exc}") from exc

        def _retryable(exc: Exception) -> bool:
            if isinstance(exc, HyperliquidRateLimitError):
                return True
            return isinstance(exc, HyperliquidHttpStatusError) and exc.retryable

        async def _with_retry() -> Any:
            attempt = 0
            delay = self._config.reconnect_initial_delay_seconds
            while True:
                try:
                    return await _call()
                except HyperliquidRateLimitError as exc:
                    attempt += 1
                    if attempt >= self._config.max_http_retries:
                        raise
                    await self._sleep(exc.retry_after_seconds or delay)
                    delay = min(delay * 2, self._config.reconnect_max_delay_seconds)
                except Exception as exc:
                    if not _retryable(exc):
                        raise
                    attempt += 1
                    if attempt >= self._config.max_http_retries:
                        raise
                    await self._sleep(delay)
                    delay = min(delay * 2, self._config.reconnect_max_delay_seconds)

        logger.debug(
            "hyperliquid_http_post",
            extra={
                "event_type": "http_request",
                "request_id": request_id,
                "network": self._config.network.value,
            },
        )
        return await _with_retry()
