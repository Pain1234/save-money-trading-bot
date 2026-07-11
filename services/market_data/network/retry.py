"""Bounded exponential backoff with injectable sleep."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

SleepFn = Callable[[float], Awaitable[None]]


async def default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    initial_delay: float,
    max_delay: float,
    is_retryable: Callable[[Exception], bool],
    sleep: SleepFn = default_sleep,
) -> T:
    attempt = 0
    delay = initial_delay
    while True:
        try:
            return await operation()
        except Exception as exc:
            attempt += 1
            if attempt >= max_attempts or not is_retryable(exc):
                raise
            await sleep(delay)
            delay = min(delay * 2, max_delay)
