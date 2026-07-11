"""Runtime state machine with persistent transitions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from paper_trading.clock import Clock, SystemClock
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState
from paper_trading.repository import PaperTradingRepository
from paper_trading.transitions import validate_runtime_transition

if TYPE_CHECKING:
    from alembic.config import Config
    from sqlalchemy.engine import Engine

    from paper_trading.config import PaperTradingConfig
    from paper_trading.lock import AdvisoryLock
    from paper_trading.recovery import RecoveryResult


@contextmanager
def _transaction_scope(session: Session) -> Iterator[None]:
    if session.in_transaction():
        with session.begin_nested():
            yield
    else:
        with session.begin():
            yield


@dataclass(frozen=True)
class RuntimeTransitionResult:
    previous: RuntimeStatus
    current: RuntimeStatus
    state: RuntimeState


class RuntimeService:
    """Manage validated runtime status transitions."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or SystemClock()

    def get_state(self) -> RuntimeState:
        state = self._repo.get_runtime_state()
        if state is None:
            raise LookupError("runtime_state not seeded")
        return state

    def transition(
        self,
        target: RuntimeStatus,
        *,
        last_error: str | None = None,
        cycle_id: UUID | None = None,
    ) -> RuntimeTransitionResult:
        current = self.get_state()
        validate_runtime_transition(current.status, target)
        now = self._clock.now()
        with _transaction_scope(self._repo.session):
            updated = self._repo.update_runtime_state(
                status=target,
                last_error=last_error if last_error is not None else current.last_error,
                started_at=now if target == RuntimeStatus.STARTING else None,
                heartbeat_at=now,
                expected_version=current.version,
            )
            self._repo.append_audit_event(
                event_type="RUNTIME_STATUS_CHANGED",
                aggregate_type="runtime_state",
                aggregate_id=updated.instance_id,
                payload_json={
                    "from": current.status.value,
                    "to": target.value,
                    "cycle_id": str(cycle_id) if cycle_id else None,
                },
                cycle_id=cycle_id,
                created_at=now,
            )
        return RuntimeTransitionResult(
            previous=current.status,
            current=target,
            state=updated,
        )

    def heartbeat(self) -> RuntimeState:
        now = self._clock.now()
        current = self.get_state()
        return self._repo.update_runtime_state(
            heartbeat_at=now,
            expected_version=current.version,
        )

    def set_paused(self, paused: bool) -> RuntimeState:
        current = self.get_state()
        with _transaction_scope(self._repo.session):
            updated = self._repo.update_runtime_state(
                paused=paused,
                expected_version=current.version,
            )
            self._repo.append_audit_event(
                event_type="RUNTIME_PAUSED" if paused else "RUNTIME_RESUMED",
                aggregate_type="runtime_state",
                aggregate_id=updated.instance_id,
                payload_json={"paused": paused},
                created_at=self._clock.now(),
            )
        return updated

    def set_kill_switch(self, enabled: bool) -> RuntimeState:
        current = self.get_state()
        with _transaction_scope(self._repo.session):
            updated = self._repo.update_runtime_state(
                kill_switch=enabled,
                expected_version=current.version,
            )
            self._repo.append_audit_event(
                event_type="KILL_SWITCH_ENABLED" if enabled else "KILL_SWITCH_DISABLED",
                aggregate_type="runtime_state",
                aggregate_id=updated.instance_id,
                payload_json={"kill_switch": enabled},
                created_at=self._clock.now(),
            )
        return updated

    def recover_on_startup(
        self,
        config: PaperTradingConfig,
        advisory_lock: AdvisoryLock,
        *,
        market_data_ready: bool,
        db_engine: Engine | None = None,
        alembic_config: Config | None = None,
    ) -> RecoveryResult:
        from paper_trading.recovery import recover_on_startup as _recover

        return _recover(
            self._repo,
            config,
            advisory_lock,
            market_data_ready=market_data_ready,
            db_engine=db_engine,
            alembic_config=alembic_config,
            clock=self._clock,
        )
