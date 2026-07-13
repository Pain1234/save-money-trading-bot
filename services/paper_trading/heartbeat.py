"""Durable, isolated worker-heartbeat persistence and lock diagnostics."""

from __future__ import annotations

import asyncio
import logging
import random
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.clock import Clock
from paper_trading.models import RuntimeState
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService

logger = logging.getLogger(__name__)

HEARTBEAT_APPLICATION_NAME = "paper-worker-heartbeat"


@dataclass(frozen=True)
class HeartbeatCommitResult:
    previous: RuntimeState
    updated: RuntimeState
    observed: RuntimeState
    attempts: int = 1


@dataclass(frozen=True)
class RuntimeLockDiagnostic:
    blocked_relation: str
    blocked_pid: int
    blocking_pid: int | None
    blocking_transaction_age_seconds: float | None
    blocking_query_age_seconds: float | None
    blocking_application_name: str | None


class HeartbeatLockTimeout(RuntimeError):
    """A retryable PostgreSQL runtime-state lock timeout."""

    def __init__(
        self,
        *,
        blocked_pid: int,
        diagnostic: RuntimeLockDiagnostic | None,
        cause: BaseException,
    ) -> None:
        super().__init__("runtime_state heartbeat lock timeout")
        self.blocked_pid = blocked_pid
        self.diagnostic = diagnostic
        self.__cause__ = cause


class HeartbeatRetryExhausted(RuntimeError):
    """The bounded heartbeat retry budget was exhausted."""

    def __init__(self, attempts: int, last_error: HeartbeatLockTimeout) -> None:
        super().__init__(f"runtime_state heartbeat failed after {attempts} attempts")
        self.attempts = attempts
        self.last_error = last_error


def _is_lock_timeout(exc: BaseException) -> bool:
    if isinstance(exc, DBAPIError):
        original = exc.orig
        sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
        if sqlstate == "55P03":
            return True
    message = str(exc).lower()
    return "lock timeout" in message or "locknotavailable" in message


def inspect_runtime_lock(
    engine: Engine,
    *,
    blocked_pid: int,
) -> RuntimeLockDiagnostic:
    """Read the exact blocker while the heartbeat backend is still waiting."""
    statement = text(
        """
        WITH target_relation AS (
            SELECT oid, relname
            FROM pg_class
            WHERE oid = to_regclass('runtime_state')
        ),
        blocked_activity AS (
            SELECT activity.pid, target_relation.relname AS blocked_relation
            FROM pg_stat_activity AS activity
            JOIN pg_locks AS relation_lock ON relation_lock.pid = activity.pid
            JOIN target_relation ON target_relation.oid = relation_lock.relation
            WHERE activity.pid = :blocked_pid
              AND relation_lock.granted
            LIMIT 1
        )
        SELECT
            blocked.pid AS blocked_pid,
            blocked.blocked_relation AS blocked_relation,
            blocker.pid AS blocking_pid,
            EXTRACT(EPOCH FROM (clock_timestamp() - blocker.xact_start)) AS xact_age,
            EXTRACT(EPOCH FROM (clock_timestamp() - blocker.query_start)) AS query_age,
            NULLIF(blocker.application_name, '') AS application_name
        FROM blocked_activity AS blocked
        LEFT JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocker_pid(pid)
            ON TRUE
        LEFT JOIN pg_stat_activity AS blocker ON blocker.pid = blocker_pid.pid
        WHERE blocked.pid = :blocked_pid
        ORDER BY blocker.xact_start NULLS LAST
        LIMIT 1
        """
    )
    with engine.connect() as connection:
        row = connection.execute(statement, {"blocked_pid": blocked_pid}).mappings().first()
    if row is None:
        return RuntimeLockDiagnostic(
            blocked_relation="runtime_state",
            blocked_pid=blocked_pid,
            blocking_pid=None,
            blocking_transaction_age_seconds=None,
            blocking_query_age_seconds=None,
            blocking_application_name=None,
        )
    return RuntimeLockDiagnostic(
        blocked_relation=str(row["blocked_relation"]),
        blocked_pid=int(row["blocked_pid"]),
        blocking_pid=(int(row["blocking_pid"]) if row["blocking_pid"] is not None else None),
        blocking_transaction_age_seconds=(
            float(row["xact_age"]) if row["xact_age"] is not None else None
        ),
        blocking_query_age_seconds=(
            float(row["query_age"]) if row["query_age"] is not None else None
        ),
        blocking_application_name=row["application_name"],
    )


def _log_lock_timeout(
    diagnostic: RuntimeLockDiagnostic | None,
    *,
    blocked_pid: int,
    attempt: int,
) -> None:
    item = diagnostic or RuntimeLockDiagnostic(
        blocked_relation="runtime_state",
        blocked_pid=blocked_pid,
        blocking_pid=None,
        blocking_transaction_age_seconds=None,
        blocking_query_age_seconds=None,
        blocking_application_name=None,
    )
    logger.warning(
        "runtime_heartbeat_lock_timeout blocked_relation=%s blocked_pid=%s "
        "blocking_pid=%s blocking_transaction_age_seconds=%s "
        "blocking_query_age_seconds=%s blocking_application_name=%s "
        "runtime_operation=heartbeat task_role=heartbeat attempt=%s",
        item.blocked_relation,
        item.blocked_pid,
        item.blocking_pid if item.blocking_pid is not None else "unknown",
        (
            f"{item.blocking_transaction_age_seconds:.3f}"
            if item.blocking_transaction_age_seconds is not None
            else "unknown"
        ),
        (
            f"{item.blocking_query_age_seconds:.3f}"
            if item.blocking_query_age_seconds is not None
            else "unknown"
        ),
        item.blocking_application_name or "unset",
        attempt,
        extra={
            "event_type": "runtime_heartbeat_lock_timeout",
            "blocked_relation": item.blocked_relation,
            "blocked_pid": item.blocked_pid,
            "blocking_pid": item.blocking_pid,
            "blocking_transaction_age_seconds": item.blocking_transaction_age_seconds,
            "blocking_query_age_seconds": item.blocking_query_age_seconds,
            "blocking_application_name": item.blocking_application_name,
            "runtime_operation": "heartbeat",
            "task_role": "heartbeat",
            "attempt": attempt,
        },
    )


def persist_runtime_heartbeat(
    session_factory: sessionmaker[Session],
    *,
    clock: Clock,
    lock_timeout_seconds: float = 1.0,
    diagnostic_delay_seconds: float = 0.05,
) -> HeartbeatCommitResult:
    """Commit in a fresh Session A and verify with an independent Session B."""
    diagnostic: list[RuntimeLockDiagnostic] = []
    timer: threading.Timer | None = None
    blocked_pid = -1
    with session_factory() as write_session:
        engine = write_session.get_bind()
        try:
            with write_session.begin():
                write_session.execute(
                    text("SELECT set_config('application_name', :name, true)"),
                    {"name": HEARTBEAT_APPLICATION_NAME},
                )
                write_session.execute(
                    text("SELECT set_config('lock_timeout', :timeout, true)"),
                    {"timeout": f"{max(lock_timeout_seconds, 0.001):.3f}s"},
                )
                blocked_pid = int(
                    write_session.execute(text("SELECT pg_backend_pid()")).scalar_one()
                )
                if isinstance(engine, Engine):
                    def collect_diagnostic() -> None:
                        try:
                            diagnostic.append(
                                inspect_runtime_lock(engine, blocked_pid=blocked_pid)
                            )
                        except Exception:
                            logger.warning(
                                "runtime_heartbeat_lock_diagnostic_failed "
                                "runtime_operation=heartbeat task_role=heartbeat",
                                extra={
                                    "event_type": "runtime_heartbeat_lock_diagnostic_failed",
                                    "runtime_operation": "heartbeat",
                                    "task_role": "heartbeat",
                                },
                            )

                    timer = threading.Timer(diagnostic_delay_seconds, collect_diagnostic)
                    timer.daemon = True
                    timer.start()

                runtime = RuntimeService(PaperTradingRepository(write_session), clock=clock)
                previous = runtime.get_state()
                updated = runtime.heartbeat()
        except Exception as exc:
            if timer is not None:
                timer.cancel()
                timer.join(timeout=max(lock_timeout_seconds, 0.1))
            write_session.rollback()
            if _is_lock_timeout(exc):
                raise HeartbeatLockTimeout(
                    blocked_pid=blocked_pid,
                    diagnostic=diagnostic[0] if diagnostic else None,
                    cause=exc,
                ) from exc
            raise
        finally:
            if timer is not None:
                timer.cancel()

    with session_factory() as verify_session:
        observed = RuntimeService(PaperTradingRepository(verify_session), clock=clock).get_state()

    if observed.heartbeat_at != updated.heartbeat_at or observed.version != updated.version:
        raise RuntimeError("committed heartbeat is not visible in a fresh database session")

    return HeartbeatCommitResult(previous=previous, updated=updated, observed=observed)


async def persist_runtime_heartbeat_with_retry(
    session_factory: sessionmaker[Session],
    *,
    clock: Clock,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.2,
    lock_timeout_seconds: float = 1.0,
    diagnostic_delay_seconds: float = 0.05,
    jitter: Callable[[float, float], float] = random.uniform,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> HeartbeatCommitResult:
    """Retry only lock timeouts, using a new closed session for every attempt."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    last_error: HeartbeatLockTimeout | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await asyncio.to_thread(
                persist_runtime_heartbeat,
                session_factory,
                clock=clock,
                lock_timeout_seconds=lock_timeout_seconds,
                diagnostic_delay_seconds=diagnostic_delay_seconds,
            )
            return HeartbeatCommitResult(
                previous=result.previous,
                updated=result.updated,
                observed=result.observed,
                attempts=attempt,
            )
        except HeartbeatLockTimeout as exc:
            last_error = exc
            _log_lock_timeout(exc.diagnostic, blocked_pid=exc.blocked_pid, attempt=attempt)
            if attempt == max_attempts:
                break
            exponential = base_delay_seconds * (2 ** (attempt - 1))
            await sleep(exponential + jitter(0.0, base_delay_seconds))
    assert last_error is not None
    raise HeartbeatRetryExhausted(max_attempts, last_error)
