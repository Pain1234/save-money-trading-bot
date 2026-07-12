"""PostgreSQL connection URL normalization for SQLAlchemy psycopg3."""

from __future__ import annotations

import os

_TARGET_PREFIX = "postgresql+psycopg://"


def normalize_postgresql_url(url: str) -> str:
    """Normalize Railway-style PostgreSQL URLs for SQLAlchemy psycopg3."""
    normalized = url.strip()
    if not normalized:
        raise ValueError("database URL must not be empty")

    if normalized.startswith(_TARGET_PREFIX):
        return normalized
    if normalized.startswith("postgresql://"):
        return _TARGET_PREFIX + normalized[len("postgresql://") :]
    if normalized.startswith("postgres://"):
        return _TARGET_PREFIX + normalized[len("postgres://") :]

    raise ValueError("unsupported database URL scheme")


def resolve_migration_database_url(
    *,
    env_url: str | None,
    fallback_url: str | None,
) -> str:
    """Resolve Alembic database URL from env override or config fallback."""
    if env_url is not None and env_url.strip():
        return normalize_postgresql_url(env_url)
    if fallback_url is None or not fallback_url.strip():
        raise ValueError("PAPER_TRADING_DATABASE_URL is required")
    return normalize_postgresql_url(fallback_url)


def resolve_database_url_from_env(
    env_name: str,
    *,
    default: str | None = None,
) -> str:
    """Read and normalize a PostgreSQL URL from the environment."""
    raw = os.environ.get(env_name)
    if raw is None or not raw.strip():
        if default is None:
            raise ValueError(f"{env_name} is required")
        return normalize_postgresql_url(default)
    return normalize_postgresql_url(raw)
