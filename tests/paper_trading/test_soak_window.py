"""Regression tests for live soak evidence scoping (OLR-007, RMR-006)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from paper_trading.soak_window import (
    capture_soak_started_at,
    create_soak_run,
    list_failed_market_event_runs_for_soak,
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
    soak_run_id: UUID | None = None,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO scheduler_runs (
                run_id, job_name, scheduled_for, started_at, completed_at,
                status, error, idempotency_key, soak_run_id
            ) VALUES (
                :run_id, :job_name, :scheduled_for, :started_at, :completed_at,
                'FAILED', :error, :idempotency_key, :soak_run_id
            )
            ON CONFLICT (job_name, scheduled_for) DO UPDATE SET
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                status = EXCLUDED.status,
                error = EXCLUDED.error,
                soak_run_id = EXCLUDED.soak_run_id
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
            "soak_run_id": soak_run_id,
        },
    )


@pytest.mark.postgres
def test_soak_run_id_ignores_historical_failed_runs(clean_production_db) -> None:
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    historical = datetime(2020, 1, 1, tzinfo=UTC)
    try:
        soak_run_id = create_soak_run(engine)
        with engine.begin() as connection:
            _insert_failed_run(
                connection,
                job_name="me:do:BTC:20200101T000000Z",
                started_at=historical,
                soak_run_id=None,
            )
            failed = list_failed_market_event_runs_for_soak(
                connection,
                soak_run_id=soak_run_id,
            )
        assert failed == []
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_soak_run_id_reports_current_failed_runs(clean_production_db) -> None:
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    try:
        soak_run_id = create_soak_run(engine)
        current = datetime(2026, 1, 2, tzinfo=UTC)
        with engine.begin() as connection:
            _insert_failed_run(
                connection,
                job_name="me:do:ETH:20260102T000000Z",
                started_at=current,
                error="current_failure",
                soak_run_id=soak_run_id,
            )
            failed = list_failed_market_event_runs_for_soak(
                connection,
                soak_run_id=soak_run_id,
            )
        assert ("me:do:ETH:20260102T000000Z", "current_failure") in failed
        assert unexpected_failed_market_event_runs(failed) == [
            ("me:do:ETH:20260102T000000Z", "current_failure"),
        ]
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_clock_skew_current_failure_detected_by_soak_run_id(clean_production_db) -> None:
    """ApplicationClock behind DB time cannot hide a current soak failure."""
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    try:
        soak_run_id = create_soak_run(engine)
        skewed_started_at = datetime(2019, 12, 31, tzinfo=UTC)
        with engine.begin() as connection:
            _insert_failed_run(
                connection,
                job_name="me:do:SOL:20260102T000000Z",
                started_at=skewed_started_at,
                error="skewed_clock_failure",
                soak_run_id=soak_run_id,
            )
            failed = list_failed_market_event_runs_for_soak(
                connection,
                soak_run_id=soak_run_id,
            )
        assert ("me:do:SOL:20260102T000000Z", "skewed_clock_failure") in failed
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_clock_skew_historical_run_not_attributed_to_new_soak(clean_production_db) -> None:
    """Recent started_at without soak_run_id must not pollute soak-run evidence."""
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    try:
        first_soak = create_soak_run(engine)
        second_soak = create_soak_run(engine)
        recent = datetime(2026, 6, 1, tzinfo=UTC)
        with engine.begin() as connection:
            _insert_failed_run(
                connection,
                job_name="me:do:BTC:20260601T000000Z",
                started_at=recent,
                error="historical_without_soak_id",
                soak_run_id=first_soak,
            )
            failed = list_failed_market_event_runs_for_soak(
                connection,
                soak_run_id=second_soak,
            )
        assert failed == []
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_multiple_soak_runs_have_unique_failed_scope(clean_production_db) -> None:
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    try:
        soak_a = create_soak_run(engine)
        soak_b = create_soak_run(engine)
        when = datetime(2026, 2, 1, tzinfo=UTC)
        with engine.begin() as connection:
            _insert_failed_run(
                connection,
                job_name="me:do:BTC:20260201T000000Z",
                started_at=when,
                error="soak_a_failure",
                soak_run_id=soak_a,
            )
            _insert_failed_run(
                connection,
                job_name="me:do:ETH:20260201T000000Z",
                started_at=when,
                error="soak_b_failure",
                soak_run_id=soak_b,
            )
            failed_a = list_failed_market_event_runs_for_soak(connection, soak_run_id=soak_a)
            failed_b = list_failed_market_event_runs_for_soak(connection, soak_run_id=soak_b)
        assert failed_a == [("me:do:BTC:20260201T000000Z", "soak_a_failure")]
        assert failed_b == [("me:do:ETH:20260201T000000Z", "soak_b_failure")]
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_timestamp_window_still_scopes_historical_runs(clean_production_db) -> None:
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
    finally:
        engine.dispose()
