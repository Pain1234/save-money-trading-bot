"""Audit event helpers for paper trading."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from paper_trading.db.orm import AuditEventRow
from paper_trading.models import AuditEvent


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def new_audit_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload_json: dict[str, Any],
    cycle_id: UUID | None = None,
    created_at: datetime | None = None,
) -> AuditEventRow:
    """Build an ORM audit event row (not yet persisted)."""
    return AuditEventRow(
        event_id=uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        cycle_id=cycle_id,
        payload_json=payload_json,
        created_at=created_at or utc_now(),
    )


def audit_row_to_domain(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        event_id=row.event_id,
        event_type=row.event_type,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        cycle_id=row.cycle_id,
        payload_json=dict(row.payload_json),
        created_at=row.created_at,
    )
