"""Helpers for scoping live soak evidence to a single run identity."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

MARKET_EVENT_JOB_PREFIXES = ("me:do:", "me:dl:", "me:dc:", "me:wc:", "me:mc:")


def read_database_timestamp(connection: Connection) -> datetime:
    return cast(datetime, connection.execute(text("SELECT clock_timestamp()")).scalar_one())


def create_soak_run(engine: Engine) -> UUID:
    """Persist a soak session marker before application startup."""
    soak_run_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO soak_runs (soak_run_id, started_at, status)
                VALUES (:soak_run_id, clock_timestamp(), 'ACTIVE')
                """
            ),
            {"soak_run_id": soak_run_id},
        )
    return soak_run_id


def complete_soak_run(engine: Engine, soak_run_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE soak_runs
                SET status = 'COMPLETED',
                    completed_at = clock_timestamp()
                WHERE soak_run_id = :soak_run_id
                """
            ),
            {"soak_run_id": soak_run_id},
        )


def capture_soak_started_at(engine: Engine) -> datetime:
    """Legacy timestamp marker retained for backward-compatible tests."""
    with engine.connect() as connection:
        started_at = read_database_timestamp(connection)
        connection.commit()
        return started_at


def list_failed_market_event_runs_for_soak(
    connection: Connection,
    *,
    soak_run_id: UUID,
) -> list[tuple[str, str | None]]:
    rows = connection.execute(
        text(
            """
            SELECT job_name, error
            FROM scheduler_runs
            WHERE status = 'FAILED'
              AND soak_run_id = :soak_run_id
              AND (
                job_name LIKE 'me:do:%'
                OR job_name LIKE 'me:dl:%'
                OR job_name LIKE 'me:dc:%'
                OR job_name LIKE 'me:wc:%'
                OR job_name LIKE 'me:mc:%'
              )
            ORDER BY job_name
            """
        ),
        {"soak_run_id": soak_run_id},
    ).fetchall()
    return [(str(row[0]), row[1]) for row in rows]


def list_failed_market_event_runs_since(
    connection: Connection,
    *,
    soak_started_at: datetime,
) -> list[tuple[str, str | None]]:
    rows = connection.execute(
        text(
            """
            SELECT job_name, error
            FROM scheduler_runs
            WHERE status = 'FAILED'
              AND started_at >= :soak_started_at
              AND (
                job_name LIKE 'me:do:%'
                OR job_name LIKE 'me:dl:%'
                OR job_name LIKE 'me:dc:%'
                OR job_name LIKE 'me:wc:%'
                OR job_name LIKE 'me:mc:%'
              )
            ORDER BY job_name
            """
        ),
        {"soak_started_at": soak_started_at},
    ).fetchall()
    return [(str(row[0]), row[1]) for row in rows]


def unexpected_failed_market_event_runs(
    failed_runs: list[tuple[str, str | None]],
    *,
    allowed: set[tuple[str, str | None]] | None = None,
) -> list[tuple[str, str | None]]:
    allow = allowed or set()
    return [item for item in failed_runs if item not in allow]
