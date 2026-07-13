"""Safe PostgreSQL identity diagnostics without connection secrets."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import URL, Engine, make_url


@dataclass(frozen=True)
class DatabaseIdentity:
    service_role: str
    database_fingerprint: str
    current_database: str
    environment_name: str | None
    alembic_revision: str | None


def database_fingerprint(database_url: str | URL) -> str:
    """Hash only host, port, and database name; never expose the source URL."""
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    host = (url.host or "").strip().lower()
    port = url.port or 5432
    database = (url.database or "").strip()
    normalized = f"{host}|{port}|{database}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def inspect_database_identity(
    engine: Engine,
    *,
    service_role: str,
    environment_name: str | None = None,
) -> DatabaseIdentity:
    """Read non-secret identity fields from the connected PostgreSQL server."""
    with engine.connect() as connection:
        current_database = str(
            connection.execute(text("SELECT current_database()"))
            .scalar_one()
        ).strip()
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one_or_none()
    resolved_environment = environment_name or os.environ.get(
        "RAILWAY_ENVIRONMENT_NAME"
    ) or os.environ.get("RAILWAY_ENVIRONMENT")
    return DatabaseIdentity(
        service_role=service_role,
        database_fingerprint=database_fingerprint(engine.url),
        current_database=current_database,
        environment_name=resolved_environment,
        alembic_revision=str(revision) if revision is not None else None,
    )


def log_database_identity(logger: logging.Logger, identity: DatabaseIdentity) -> None:
    """Emit only the reviewed safe fields in both text and structured form."""
    environment_name = identity.environment_name or "unset"
    alembic_revision = identity.alembic_revision or "missing"
    logger.info(
        "database_identity service_role=%s database_fingerprint=%s "
        "current_database=%s environment_name=%s alembic_revision=%s",
        identity.service_role,
        identity.database_fingerprint,
        identity.current_database,
        environment_name,
        alembic_revision,
        extra={
            "event_type": "database_identity",
            "service_role": identity.service_role,
            "database_fingerprint": identity.database_fingerprint,
            "current_database": identity.current_database,
            "environment_name": environment_name,
            "alembic_revision": alembic_revision,
        },
    )
