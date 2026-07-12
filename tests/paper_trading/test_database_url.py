"""Tests for PostgreSQL URL normalization (Railway psycopg3 driver)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from paper_trading.config import PaperTradingConfig
from paper_trading.database_url import (
    normalize_postgresql_url,
    resolve_database_url_from_env,
    resolve_migration_database_url,
)
from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SECRET_PASSWORD = "p@ss#word"
ENCODED_PASSWORD = "p%40ss%23word"
HOST = "db.example.internal"
DATABASE = "paper_trading"


@pytest.mark.parametrize(
    "scheme",
    ["postgres://", "postgresql://"],
)
def test_railway_schemes_normalize_to_psycopg3(scheme: str) -> None:
    url = f"{scheme}user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}?sslmode=require"
    normalized = normalize_postgresql_url(url)
    assert normalized == (
        f"postgresql+psycopg://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}?sslmode=require"
    )


def test_psycopg3_url_unchanged() -> None:
    url = f"postgresql+psycopg://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}"
    assert normalize_postgresql_url(url) == url


def test_url_encoded_password_preserved() -> None:
    url = f"postgresql://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}"
    normalized = normalize_postgresql_url(url)
    assert normalized == f"postgresql+psycopg://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}"


def test_query_parameters_preserved() -> None:
    url = f"postgres://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}?sslmode=require&connect_timeout=10"
    normalized = normalize_postgresql_url(url)
    assert normalized.endswith("?sslmode=require&connect_timeout=10")


def test_whitespace_trimmed() -> None:
    url = f"  postgresql://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}  "
    normalized = normalize_postgresql_url(url)
    assert normalized == f"postgresql+psycopg://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}"


def test_empty_url_raises() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_postgresql_url("   ")


@pytest.mark.parametrize("url", ["sqlite:///tmp.db", "mysql://user:pass@host/db", "http://example.com"])
def test_unsupported_scheme_raises(url: str) -> None:
    with pytest.raises(ValueError, match="unsupported database URL scheme"):
        normalize_postgresql_url(url)


def test_error_messages_do_not_leak_url_or_secrets() -> None:
    with pytest.raises(ValueError, match="unsupported database URL scheme") as exc_info:
        normalize_postgresql_url(f"oracle://user:{SECRET_PASSWORD}@{HOST}/{DATABASE}")
    message = str(exc_info.value)
    assert SECRET_PASSWORD not in message
    assert HOST not in message


def test_sqlalchemy_uses_psycopg_driver_not_psycopg2() -> None:
    url = normalize_postgresql_url(
        f"postgresql://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}"
    )
    engine = create_engine(url)
    try:
        assert engine.driver == "psycopg"
        assert "psycopg2" not in engine.url.drivername
    finally:
        engine.dispose()


def test_config_from_env_normalizes_railway_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        f"postgresql://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}",
    )
    config = PaperTradingConfig.from_env()
    assert str(config.database_url).startswith("postgresql+psycopg://")
    assert ENCODED_PASSWORD in str(config.database_url)


def test_resolve_database_url_from_env_requires_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_TRADING_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="PAPER_TRADING_DATABASE_URL is required"):
        resolve_database_url_from_env("PAPER_TRADING_DATABASE_URL")


def test_alembic_get_url_normalizes_env_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        f"postgres://user:{ENCODED_PASSWORD}@{HOST}:5432/{DATABASE}",
    )
    assert resolve_migration_database_url(
        env_url=os.environ.get("PAPER_TRADING_DATABASE_URL"),
        fallback_url="postgresql://postgres:postgres@localhost:5432/paper_trading",
    ).startswith("postgresql+psycopg://")

    monkeypatch.delenv("PAPER_TRADING_DATABASE_URL", raising=False)
    assert resolve_migration_database_url(
        env_url=os.environ.get("PAPER_TRADING_DATABASE_URL"),
        fallback_url="postgresql://postgres:postgres@localhost:5432/paper_trading",
    ).startswith("postgresql+psycopg://")


def test_local_example_env_resolves_to_psycopg3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PAPER_TRADING_DATABASE_URL",
        "postgresql://user:pass@localhost:5432/example",
    )
    resolved = resolve_database_url_from_env("PAPER_TRADING_DATABASE_URL")
    assert resolved == "postgresql+psycopg://user:pass@localhost:5432/example"
    assert "postgresql+psycopg" in resolved
