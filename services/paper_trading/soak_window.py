"""Helpers for scoping live soak evidence to a single run window."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

MARKET_EVENT_JOB_PREFIXES = ("me:do:", "me:dl:", "me:dc:", "me:wc:", "me:mc:")


def read_database_timestamp(connection: Connection) -> datetime:
    return cast(datetime, connection.execute(text("SELECT clock_timestamp()")).scalar_one())


def capture_soak_started_at(engine: Engine) -> datetime:
    with engine.connect() as connection:
        started_at = read_database_timestamp(connection)
        connection.commit()
        return started_at


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
