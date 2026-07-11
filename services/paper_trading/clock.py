"""Injectable clock for deterministic paper trading lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """UTC clock used by orchestrator lifecycle code."""

    def now(self) -> datetime:
        """Return current UTC time."""


class SystemClock:
    """Production clock backed by system time."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class FixedClock:
    """Deterministic clock for tests."""

    def __init__(self, fixed_time: datetime) -> None:
        if fixed_time.tzinfo is None:
            raise ValueError("fixed_time must be timezone-aware UTC")
        self._fixed_time = fixed_time.astimezone(UTC)

    def now(self) -> datetime:
        return self._fixed_time

    def advance(self, *, seconds: int = 0) -> None:
        from datetime import timedelta

        self._fixed_time = self._fixed_time + timedelta(seconds=seconds)
