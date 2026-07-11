"""Simple async HTTP concurrency limiter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AsyncRateLimiter:
    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        await self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
