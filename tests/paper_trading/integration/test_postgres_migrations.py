"""PostgreSQL migration integration tests."""

from __future__ import annotations

from decimal import Decimal

from alembic import command
from alembic.config import Config
from paper_trading.db.orm import RUNTIME_SINGLETON_ID, WALLET_SINGLETON_ID
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from tests.paper_trading.conftest import requires_postgres


@requires_postgres
def test_migration_upgrade_to_head(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    tables = set(inspector.get_table_names())
    assert "paper_wallet" in tables
    assert "runtime_state" in tables


@requires_postgres
def test_migration_downgrade_to_base(alembic_config: Config, migrated_engine: Engine) -> None:
    try:
        command.downgrade(alembic_config, "base")
    except NotImplementedError:
        command.stamp(alembic_config, "010_market_data_datasets")
        command.downgrade(alembic_config, "base")
    inspector = inspect(migrated_engine)
    assert "paper_wallet" not in inspector.get_table_names()
    command.upgrade(alembic_config, "head")


@requires_postgres
def test_seed_runtime_and_wallet(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        runtime = conn.execute(
            text("SELECT status FROM runtime_state WHERE instance_id = :id"),
            {"id": RUNTIME_SINGLETON_ID},
        ).scalar_one()
        assert runtime == "STOPPED"
        cash = conn.execute(
            text("SELECT cash FROM paper_wallet WHERE wallet_id = :id"),
            {"id": WALLET_SINGLETON_ID},
        ).scalar_one()
        assert Decimal(str(cash)) == Decimal("100000")
