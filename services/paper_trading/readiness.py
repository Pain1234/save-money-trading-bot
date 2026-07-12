"""Composite readiness checks for paper trading orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from paper_trading.clock import Clock, SystemClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import AdvisoryLock
from paper_trading.models import RuntimeState
from paper_trading.repository import PaperTradingRepository


@dataclass(frozen=True)
class ReadinessSnapshot:
    process_liveness: bool
    runtime_readiness: bool
    entry_readiness: bool
    reasons: tuple[str, ...]


class ReadinessService:
    """Evaluate liveness, runtime readiness, and entry readiness separately."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        config: PaperTradingConfig,
        *,
        clock: Clock | None = None,
        db_engine: Engine | None = None,
        alembic_config: Config | None = None,
    ) -> None:
        self._repo = repository
        self._config = config
        self._clock = clock or SystemClock()
        self._db_engine = db_engine
        self._alembic_config = alembic_config

    def evaluate(
        self,
        *,
        market_data_ready: bool,
        advisory_lock: AdvisoryLock | None = None,
        scheduler_active: bool = False,
        recovery_active: bool = False,
    ) -> ReadinessSnapshot:
        reasons: list[str] = []
        runtime = self._repo.get_runtime_state()
        if runtime is None:
            return ReadinessSnapshot(False, False, False, ("runtime_state_missing",))

        liveness = self._process_liveness(runtime, reasons)
        runtime_ready = self._runtime_readiness(
            runtime,
            market_data_ready=market_data_ready,
            advisory_lock=advisory_lock,
            scheduler_active=scheduler_active,
            recovery_active=recovery_active,
            reasons=reasons,
        )
        entry_ready = runtime_ready and self._entry_readiness(runtime, reasons)
        return ReadinessSnapshot(
            process_liveness=liveness,
            runtime_readiness=runtime_ready,
            entry_readiness=entry_ready,
            reasons=tuple(reasons),
        )

    def _process_liveness(self, runtime: RuntimeState, reasons: list[str]) -> bool:
        if runtime.status in {RuntimeStatus.FAILED, RuntimeStatus.STOPPED}:
            reasons.append("runtime_not_live")
            return False
        return True

    def _runtime_readiness(
        self,
        runtime: RuntimeState,
        *,
        market_data_ready: bool,
        advisory_lock: AdvisoryLock | None,
        scheduler_active: bool,
        recovery_active: bool,
        reasons: list[str],
    ) -> bool:
        ok = True
        if runtime.status != RuntimeStatus.READY:
            reasons.append("runtime_not_ready")
            ok = False
        if not market_data_ready:
            reasons.append("market_data_not_ready")
            ok = False
        if not self._database_ready(reasons):
            ok = False
        if not self._schema_at_head(reasons):
            ok = False
        if advisory_lock is not None and not advisory_lock.held:
            reasons.append("advisory_lock_not_held")
            ok = False
        if self._config.scheduler_enabled and not scheduler_active:
            reasons.append("scheduler_not_active")
            ok = False
        if runtime.last_error:
            reasons.append("last_error_set")
            ok = False
        if recovery_active:
            reasons.append("recovery_active")
            ok = False
        if self._orphan_scheduler_run(reasons):
            ok = False
        if self._permanent_configuration_failure(reasons):
            ok = False
        if not self._heartbeat_fresh(runtime, reasons):
            ok = False
        return ok

    def _entry_readiness(self, runtime: RuntimeState, reasons: list[str]) -> bool:
        ok = True
        if runtime.paused:
            reasons.append("paused")
            ok = False
        if runtime.kill_switch:
            reasons.append("kill_switch")
            ok = False
        if self._permanent_configuration_failure(reasons):
            ok = False
        return ok

    def _heartbeat_fresh(self, runtime: RuntimeState, reasons: list[str]) -> bool:
        age = self._clock.now() - runtime.heartbeat_at
        if age > timedelta(seconds=self._config.stale_runtime_threshold_seconds):
            reasons.append("stale_heartbeat")
            return False
        return True

    def _database_ready(self, reasons: list[str]) -> bool:
        if self._db_engine is None:
            return True
        try:
            with self._db_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            reasons.append("database_unreachable")
            return False

    def _schema_at_head(self, reasons: list[str]) -> bool:
        if self._db_engine is None or self._alembic_config is None:
            return True
        try:
            script = ScriptDirectory.from_config(self._alembic_config)
            head = script.get_current_head()
            with self._db_engine.connect() as conn:
                current = conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar_one_or_none()
            if current != head:
                reasons.append("migration_not_at_head")
                return False
            return True
        except Exception:
            reasons.append("migration_check_failed")
            return False

    def _orphan_scheduler_run(self, reasons: list[str]) -> bool:
        orphan = self._repo.get_running_scheduler_runs()
        if orphan:
            reasons.append("orphan_scheduler_run")
            return True
        return False

    def _permanent_configuration_failure(self, reasons: list[str]) -> bool:
        failures = self._repo.list_permanent_configuration_failures()
        if failures:
            reasons.append("permanent_configuration_failure")
            return True
        return False

    def stops_allowed_when_paused(self) -> bool:
        return True

    def entry_allowed(self, snapshot: ReadinessSnapshot) -> bool:
        return snapshot.entry_readiness
