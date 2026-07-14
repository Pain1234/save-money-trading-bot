"""Shared fixtures for paper trading tests."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

DEFAULT_PG_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test"

_DEFAULT_SYMBOL_CONSTRAINTS_JSON = json.dumps(
    {
        "BTC": {
            "quantity_step": "0.001",
            "minimum_quantity": "0.001",
            "minimum_notional": "10",
            "price_tick_size": "0.01",
        },
        "ETH": {
            "quantity_step": "0.001",
            "minimum_quantity": "0.001",
            "minimum_notional": "10",
            "price_tick_size": "0.01",
        },
        "SOL": {
            "quantity_step": "0.001",
            "minimum_quantity": "0.001",
            "minimum_notional": "10",
            "price_tick_size": "0.01",
        },
    }
)

_PAPER_TRADING_RESET_TABLES = (
    "audit_events",
    "funding_events",
    "portfolio_snapshots",
    "position_stop_history",
    "paper_fills",
    "paper_orders",
    "paper_positions",
    "trade_intents",
    "strategy_evaluations",
    "scheduler_runs",
)

_MARKET_DATA_RESET_TABLES = (
    "market_data_normalized_candles",
    "market_data_datasets",
    "market_data_raw_artifacts",
)

ALLOWED_POSTGRES_TEST_DATABASE = "paper_trading_test"


def assert_postgres_test_database_safe(connection) -> tuple[str, str]:
    """Fail closed before destructive test resets unless connected DB is the test database."""
    row = connection.execute(
        text("SELECT current_database(), current_user")
    ).one()
    db_name, db_user = str(row[0]), str(row[1])
    if db_name != ALLOWED_POSTGRES_TEST_DATABASE:
        raise RuntimeError(
            "Refusing destructive postgres reset: connected database is "
            f"{db_name!r}, expected {ALLOWED_POSTGRES_TEST_DATABASE!r}. "
            "No tables were modified."
        )
    return db_name, db_user


def _reset_postgres_trading_state(engine: Engine) -> None:
    tables = ", ".join(_PAPER_TRADING_RESET_TABLES)
    with engine.connect() as conn:
        assert_postgres_test_database_safe(conn)
        conn.execute(text("SET lock_timeout = '2s'"))
        conn.execute(text("SET statement_timeout = '5s'"))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.execute(
            text(
                """
                UPDATE paper_wallet
                SET cash = :cash,
                    total_realized_pnl = 0,
                    total_fees = 0,
                    total_funding = 0,
                    total_slippage = 0,
                    version = 1
                """
            ),
            {"cash": Decimal("100000")},
        )
        conn.execute(
            text(
                """
                UPDATE runtime_state
                SET status = 'STOPPED',
                    kill_switch = false,
                    paused = false,
                    version = 1
                """
            )
        )
        conn.commit()


def _reset_postgres_market_data_state(engine: Engine) -> None:
    with engine.connect() as conn:
        assert_postgres_test_database_safe(conn)
        exists = conn.execute(
            text("SELECT to_regclass('public.market_data_datasets') IS NOT NULL")
        ).scalar()
        if not exists:
            return
        tables = ", ".join(_MARKET_DATA_RESET_TABLES)
        conn.execute(text("SET lock_timeout = '2s'"))
        conn.execute(text("SET statement_timeout = '5s'"))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.commit()


def _postgres_url() -> str:
    from paper_trading.database_url import resolve_database_url_from_env

    return resolve_database_url_from_env(
        "PAPER_TRADING_DATABASE_URL",
        default=DEFAULT_PG_URL,
    )


def _ensure_postgres_test_env() -> None:
    os.environ.setdefault("PAPER_SYMBOL_CONSTRAINTS_JSON", _DEFAULT_SYMBOL_CONSTRAINTS_JSON)


def postgres_available() -> bool:
    if os.environ.get("PAPER_TRADING_DATABASE_URL") is None:
        return False
    try:
        engine = create_engine(
            _postgres_url(),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


_postgres_available_cache: bool | None = None


def _is_postgres_available() -> bool:
    global _postgres_available_cache
    if _postgres_available_cache is None:
        _postgres_available_cache = postgres_available()
    return _postgres_available_cache


requires_postgres = pytest.mark.postgres(
    pytest.mark.skipif(
        not _is_postgres_available(),
        reason="PostgreSQL not available at PAPER_TRADING_DATABASE_URL",
    )
)


def pytest_configure(config: pytest.Config) -> None:
    _ensure_postgres_test_env()
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is not None:
        raise RuntimeError(
            "PostgreSQL paper-trading tests are not safe with pytest-xdist workers "
            f"({worker!r}) against a shared database. Run release gates with "
            "`python -m pytest tests/paper_trading -m postgres -n 1` or assign "
            "one database per worker."
        )


@pytest.fixture(autouse=True)
def _reset_postgres_trading_tables_before_test(request: pytest.FixtureRequest) -> Iterator[None]:
    if "postgres" not in request.node.keywords or not _is_postgres_available():
        yield
        return
    engine: Engine = request.getfixturevalue("migrated_engine")
    _reset_postgres_trading_state(engine)
    _reset_postgres_market_data_state(engine)
    yield


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _postgres_url())
    return cfg


@pytest.fixture(scope="session")
def migrated_engine(alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    yield engine
    try:
        command.downgrade(alembic_config, "base")
    except NotImplementedError:
        command.stamp(alembic_config, "010_market_data_datasets")
        command.downgrade(alembic_config, "base")
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def postgres_commit_session(migrated_engine: Engine) -> Iterator[Session]:
    """Session without outer rollback wrapper — commits visible across connections."""
    session = Session(bind=migrated_engine, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _reset_inmemory_lock() -> Iterator[None]:
    from paper_trading.app_state import reset_app_state
    from paper_trading.lock import InMemoryAdvisoryLock

    reset_app_state()
    InMemoryAdvisoryLock.reset()
    yield
    reset_app_state()
    InMemoryAdvisoryLock.reset()


@pytest.fixture
def clean_production_db(migrated_engine: Engine) -> None:
    """Clear stuck scheduler runs and fairness deferrals before integration tests."""
    fairness_cursor_id = "00000000-0000-0000-0000-000000000010"
    try:
        with migrated_engine.connect() as conn:
            conn.execute(text("SET lock_timeout = '1s'"))
            conn.execute(text("SET statement_timeout = '2s'"))
            conn.execute(
                text(
                    "UPDATE scheduler_runs SET status = 'FAILED', error = 'test_cleanup' "
                    "WHERE status = 'RUNNING'"
                )
            )
            conn.execute(text("DELETE FROM market_event_group_state"))
            conn.execute(
                text(
                    "UPDATE market_event_fairness_cursor "
                    "SET group_rotation_cursor = 0, updated_at = clock_timestamp() "
                    "WHERE cursor_id = :cursor_id"
                ),
                {"cursor_id": fairness_cursor_id},
            )
            conn.commit()
    except Exception:
        pytest.skip("PostgreSQL not writable (stale locks); restart DB or clear sessions")


@pytest.fixture
def postgres_runtime_writable(migrated_engine: Engine) -> None:
    """Skip integration tests when runtime_state is locked by a stale session."""
    try:
        with migrated_engine.connect() as conn:
            conn.execute(text("SET lock_timeout = '1s'"))
            conn.execute(text("SELECT 1 FROM runtime_state FOR UPDATE NOWAIT"))
            conn.rollback()
    except Exception:
        pytest.skip("runtime_state locked; restart PostgreSQL or clear stale sessions")


@pytest.fixture
def e2e_harness(db_session: Session):
    from paper_trading.repository import PaperTradingRepository

    from tests.paper_trading.e2e.helpers import PaperE2EHarness, paper_config_from_env

    harness = PaperE2EHarness(
        PaperTradingRepository(db_session),
        paper_config_from_env(_postgres_url()),
    )
    harness.set_runtime_ready()
    return harness
