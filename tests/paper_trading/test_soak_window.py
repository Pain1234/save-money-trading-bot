"""Regression tests for live soak evidence scoping (OLR-007)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from paper_trading.soak_window import (
    capture_soak_started_at,
    list_failed_market_event_runs_since,
    unexpected_failed_market_event_runs,
)
from sqlalchemy import create_engine, text

from tests.paper_trading.conftest import requires_postgres

pytestmark = [requires_postgres, pytest.mark.postgres]


def _postgres_url() -> str:
    import os

    url = os.environ.get("PAPER_TRADING_DATABASE_URL")
    assert url
    return url


def _insert_failed_run(
    connection,
    *,
    job_name: str,
    started_at: datetime,
    error: str = "historical_failure",
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO scheduler_runs (
                run_id, job_name, scheduled_for, started_at, completed_at,
                status, error, idempotency_key
            ) VALUES (
                :run_id, :job_name, :scheduled_for, :started_at, :completed_at,
                'FAILED', :error, :idempotency_key
            )
            ON CONFLICT (job_name, scheduled_for) DO UPDATE SET
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                status = EXCLUDED.status,
                error = EXCLUDED.error
            """
        ),
        {
            "run_id": uuid4(),
            "job_name": job_name,
            "scheduled_for": started_at,
            "started_at": started_at,
            "completed_at": started_at + timedelta(seconds=1),
            "error": error,
            "idempotency_key": f"{job_name}:{started_at.isoformat()}",
        },
    )


@pytest.mark.postgres
def test_current_soak_window_ignores_historical_failed_runs(clean_production_db) -> None:
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    historical = datetime(2020, 1, 1, tzinfo=UTC)
    try:
        with engine.begin() as connection:
            _insert_failed_run(
                connection,
                job_name="me:do:BTC:20200101T000000Z",
                started_at=historical,
            )
            soak_started_at = capture_soak_started_at(engine)
            failed = list_failed_market_event_runs_since(
                connection,
                soak_started_at=soak_started_at,
            )
        assert failed == []
        assert unexpected_failed_market_event_runs(failed) == []
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_current_soak_window_reports_new_failed_runs(clean_production_db) -> None:
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    historical = datetime(2020, 1, 2, tzinfo=UTC)
    try:
        with engine.begin() as connection:
            soak_started_at = capture_soak_started_at(engine)
            _insert_failed_run(
                connection,
                job_name="me:do:BTC:20200102T000000Z",
                started_at=historical,
            )
            current = soak_started_at + timedelta(seconds=1)
            _insert_failed_run(
                connection,
                job_name="me:do:ETH:20260102T000000Z",
                started_at=current,
                error="current_failure",
            )
            failed = list_failed_market_event_runs_since(
                connection,
                soak_started_at=soak_started_at,
            )
        assert ("me:do:ETH:20260102T000000Z", "current_failure") in failed
        assert unexpected_failed_market_event_runs(failed) == [
            ("me:do:ETH:20260102T000000Z", "current_failure"),
        ]
    finally:
        engine.dispose()
