"""Durable worker-heartbeat persistence and cross-session verification."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from paper_trading.clock import Clock
from paper_trading.models import RuntimeState
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService


@dataclass(frozen=True)
class HeartbeatCommitResult:
    previous: RuntimeState
    updated: RuntimeState
    observed: RuntimeState


def persist_runtime_heartbeat(
    session_factory: sessionmaker[Session],
    *,
    clock: Clock,
) -> HeartbeatCommitResult:
    """Commit in Session A and prove the new value is visible in fresh Session B."""
    with session_factory() as write_session:
        runtime = RuntimeService(PaperTradingRepository(write_session), clock=clock)
        previous = runtime.get_state()
        updated = runtime.heartbeat()
        write_session.commit()

    with session_factory() as verify_session:
        observed = RuntimeService(PaperTradingRepository(verify_session), clock=clock).get_state()

    if (
        observed.heartbeat_at != updated.heartbeat_at
        or observed.version != updated.version
    ):
        raise RuntimeError("committed heartbeat is not visible in a fresh database session")

    return HeartbeatCommitResult(
        previous=previous,
        updated=updated,
        observed=observed,
    )
