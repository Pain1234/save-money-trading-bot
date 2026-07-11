"""PostgreSQL advisory lock for single-scheduler enforcement."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


class AdvisoryLock(Protocol):
    """Exclusive scheduler lock interface."""

    def try_acquire(self) -> bool:
        """Attempt to acquire lock without blocking."""

    def release(self) -> None:
        """Release lock if held (idempotent)."""

    @property
    def held(self) -> bool:
        """Whether this instance currently holds the lock."""


class PostgresAdvisoryLock:
    """
    PostgreSQL advisory lock bound to a dedicated connection.

    The connection must remain open while the lock is held.
    """

    def __init__(self, engine: Engine, lock_id: int) -> None:
        self._engine = engine
        self._lock_id = lock_id
        self._connection: Connection | None = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def try_acquire(self) -> bool:
        if self._held:
            return True
        self._connection = self._engine.connect()
        acquired = self._connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": self._lock_id},
        ).scalar_one()
        if acquired:
            self._held = True
            return True
        self._connection.close()
        self._connection = None
        return False

    def release(self) -> None:
        if not self._held or self._connection is None:
            return
        self._connection.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": self._lock_id},
        )
        self._connection.close()
        self._connection = None
        self._held = False

    def __enter__(self) -> PostgresAdvisoryLock:
        if not self.try_acquire():
            raise RuntimeError("advisory lock not acquired")
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


class InMemoryAdvisoryLock:
    """Test double for offline scheduler lock tests."""

    _global_holder: str | None = None

    def __init__(self, owner: str = "test") -> None:
        self._owner = owner
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def try_acquire(self) -> bool:
        if InMemoryAdvisoryLock._global_holder is None:
            InMemoryAdvisoryLock._global_holder = self._owner
            self._held = True
            return True
        return InMemoryAdvisoryLock._global_holder == self._owner

    def release(self) -> None:
        if self._held and InMemoryAdvisoryLock._global_holder == self._owner:
            InMemoryAdvisoryLock._global_holder = None
        self._held = False

    @classmethod
    def reset(cls) -> None:
        cls._global_holder = None
