"""Regression tests for destructive postgres fixture safety guards."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from tests.paper_trading.conftest import (
    _PAPER_TRADING_RESET_TABLES,
    ALLOWED_POSTGRES_TEST_DATABASE,
    _postgres_url,
    _reset_postgres_trading_state,
    assert_postgres_test_database_safe,
    requires_postgres,
)

pytestmark = requires_postgres


def test_assert_safe_when_current_database_is_paper_trading_test(migrated_engine) -> None:
    with migrated_engine.connect() as conn:
        db_name, db_user = assert_postgres_test_database_safe(conn)
    assert db_name == ALLOWED_POSTGRES_TEST_DATABASE
    assert db_name == "paper_trading_test"
    assert isinstance(db_user, str)


def test_assert_unsafe_when_current_database_is_not_paper_trading_test() -> None:
    connection = MagicMock()
    connection.execute.return_value.one.return_value = ("production_db", "postgres")
    with pytest.raises(RuntimeError, match="Refusing destructive postgres reset"):
        assert_postgres_test_database_safe(connection)
    connection.execute.assert_called_once()


def test_reset_postgres_trading_state_refuses_wrong_database(monkeypatch) -> None:
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn

    def _reject(_conn):
        raise RuntimeError(
            "Refusing destructive postgres reset: connected database is "
            "'production_db', expected 'paper_trading_test'. No tables were modified."
        )

    monkeypatch.setattr(
        "tests.paper_trading.conftest.assert_postgres_test_database_safe",
        _reject,
    )
    with pytest.raises(RuntimeError, match="No tables were modified"):
        _reset_postgres_trading_state(engine)
    conn.execute.assert_not_called()


@pytest.mark.postgres
def test_reset_allowed_on_configured_test_database(migrated_engine) -> None:
    with migrated_engine.connect() as conn:
        db_name, _ = assert_postgres_test_database_safe(conn)
        conn.execute(
            text(
                "INSERT INTO scheduler_runs "
                "(run_id, job_name, scheduled_for, started_at, status, idempotency_key) "
                "VALUES (gen_random_uuid(), 'safety_probe', NOW(), NOW(), 'COMPLETED', 'probe')"
            )
        )
        conn.commit()
        before = conn.execute(text("SELECT COUNT(*) FROM scheduler_runs")).scalar_one()

    _reset_postgres_trading_state(migrated_engine)

    with migrated_engine.connect() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM scheduler_runs")).scalar_one()
        wallet_cash = conn.execute(text("SELECT cash FROM paper_wallet LIMIT 1")).scalar_one()
    assert before >= 1
    assert after == 0
    assert wallet_cash == Decimal("100000")


@pytest.mark.postgres
def test_manipulated_url_with_wrong_db_name_aborts_before_truncate(monkeypatch) -> None:
    wrong_url = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", wrong_url)
    engine = create_engine(wrong_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            actual_db = conn.execute(text("SELECT current_database()")).scalar_one()
        if actual_db == ALLOWED_POSTGRES_TEST_DATABASE:
            pytest.skip("URL pointed at postgres DB name but connection resolved to test DB")
        with pytest.raises(RuntimeError, match="Refusing destructive postgres reset"):
            _reset_postgres_trading_state(engine)
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_failed_safety_check_leaves_scheduler_runs_unmodified(migrated_engine, monkeypatch) -> None:
    with migrated_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO scheduler_runs "
                "(run_id, job_name, scheduled_for, started_at, status, idempotency_key) "
                "VALUES (gen_random_uuid(), 'safety_guard_probe', NOW(), NOW(), 'COMPLETED', 'x')"
            )
        )
        conn.commit()
        before = conn.execute(
            text("SELECT COUNT(*) FROM scheduler_runs WHERE job_name = 'safety_guard_probe'")
        ).scalar_one()

    def _reject(_conn):
        raise RuntimeError("Refusing destructive postgres reset")

    monkeypatch.setattr(
        "tests.paper_trading.conftest.assert_postgres_test_database_safe",
        _reject,
    )
    with pytest.raises(RuntimeError, match="Refusing destructive postgres reset"):
        _reset_postgres_trading_state(migrated_engine)

    with migrated_engine.connect() as conn:
        after = conn.execute(
            text("SELECT COUNT(*) FROM scheduler_runs WHERE job_name = 'safety_guard_probe'")
        ).scalar_one()
    assert before == after == 1


def test_reset_tables_list_is_explicit() -> None:
    assert "scheduler_runs" in _PAPER_TRADING_RESET_TABLES
    assert "paper_wallet" not in _PAPER_TRADING_RESET_TABLES


def test_postgres_url_uses_env_when_set(monkeypatch) -> None:
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", "postgresql+psycopg://localhost/test")
    assert _postgres_url() == "postgresql+psycopg://localhost/test"
