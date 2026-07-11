"""Deterministic recovery and consistency checks for paper trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from paper_trading.clock import Clock, SystemClock
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import PaperOrderRow
from paper_trading.enums import (
    PaperOrderStatus,
    PaperPositionStatus,
    RuntimeStatus,
    TradeIntentStatus,
)
from paper_trading.lock import AdvisoryLock
from paper_trading.portfolio import PortfolioSnapshotService
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService, _transaction_scope
from paper_trading.transitions import TERMINAL_INTENT_STATUSES


class IssueSeverity(StrEnum):
    AUTO_REPAIRABLE = "AUTO_REPAIRABLE"
    MANUAL = "MANUAL"
    FATAL = "FATAL"


@dataclass(frozen=True)
class ConsistencyIssue:
    code: str
    severity: IssueSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    final_status: RuntimeStatus
    issues: tuple[ConsistencyIssue, ...]
    repairs_applied: tuple[str, ...]
    entry_readiness: bool


class RecoveryService:
    """Run consistency checks and controlled auto-repairs on startup."""

    _recovery_active: bool = False

    def __init__(
        self,
        repository: PaperTradingRepository,
        config: PaperTradingConfig,
        *,
        runtime: RuntimeService | None = None,
        clock: Clock | None = None,
        db_engine: Engine | None = None,
        alembic_config: Config | None = None,
    ) -> None:
        self._repo = repository
        self._config = config
        self._runtime = runtime or RuntimeService(repository, clock=clock)
        self._clock = clock or SystemClock()
        self._db_engine = db_engine
        self._alembic_config = alembic_config
        self._snapshots = PortfolioSnapshotService(repository)

    @classmethod
    def is_recovery_active(cls) -> bool:
        return cls._recovery_active

    def run_consistency_checks(self) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []
        self._check_orphan_scheduler_runs(issues)
        self._check_stale_heartbeat(issues)
        self._check_multiple_open_positions(issues)
        self._check_intent_order_fill_chain(issues)
        self._check_position_references(issues)
        self._check_stop_invariants(issues)
        self._check_duplicate_fills(issues)
        return issues

    def apply_auto_repairs(self, issues: list[ConsistencyIssue]) -> list[str]:
        repairs: list[str] = []
        now = self._clock.now()
        for issue in issues:
            if issue.severity != IssueSeverity.AUTO_REPAIRABLE:
                continue
            if issue.code == "orphan_scheduler_run":
                count = self._repo.fail_orphan_scheduler_runs(completed_at=now)
                if count:
                    repairs.append(f"marked_{count}_orphan_scheduler_runs_failed")
            elif issue.code == "open_order_with_fill":
                order_id = UUID(issue.details["paper_order_id"])
                self._repo.update_order_status(
                    order_id,
                    PaperOrderStatus.FILLED.value,
                    remaining_quantity=issue.details.get("remaining_quantity", 0),
                    updated_at=now,
                )
                repairs.append(f"order_{order_id}_set_filled")
            elif issue.code == "filled_intent_without_status":
                intent_id = UUID(issue.details["intent_id"])
                self._repo.update_intent_status(
                    intent_id,
                    TradeIntentStatus.FILLED.value,
                    updated_at=now,
                )
                repairs.append(f"intent_{intent_id}_set_filled")
            elif issue.code == "stale_runtime_heartbeat":
                runtime = self._repo.get_runtime_state()
                if runtime is not None:
                    self._repo.update_runtime_state(
                        heartbeat_at=now,
                        expected_version=runtime.version,
                    )
                    repairs.append("runtime_heartbeat_refreshed")
        return repairs

    def recover_on_startup(
        self,
        advisory_lock: AdvisoryLock,
        *,
        market_data_ready: bool,
    ) -> RecoveryResult:
        if not advisory_lock.held and not advisory_lock.try_acquire():
            raise RuntimeError("advisory lock required for recovery")

        if RecoveryService._recovery_active:
            raise RuntimeError("recovery already in progress")

        RecoveryService._recovery_active = True
        repairs: list[str] = []
        try:
            runtime = self._runtime.get_state()
            if runtime.status == RuntimeStatus.READY:
                issues = self.run_consistency_checks()
                repairs.extend(self.apply_auto_repairs(issues))
                issues = self.run_consistency_checks()
                fatal = [i for i in issues if i.severity == IssueSeverity.FATAL]
                manual = [i for i in issues if i.severity == IssueSeverity.MANUAL]
                if fatal:
                    self._fail_recovery(fatal[0].code)
                    return self._build_result(RuntimeStatus.FAILED, issues, repairs)
                if manual or not market_data_ready:
                    self._runtime.transition(
                        RuntimeStatus.DEGRADED,
                        last_error=manual[0].code if manual else "market_data_not_ready",
                    )
                    return self._build_result(RuntimeStatus.DEGRADED, issues, repairs)
                return self._build_result(RuntimeStatus.READY, issues, repairs)

            if runtime.status == RuntimeStatus.STOPPED:
                self._runtime.transition(RuntimeStatus.STARTING)
            self._runtime.transition(RuntimeStatus.RECOVERING)

            if not self._migration_at_head():
                self._fail_recovery("migration_not_at_head")
                return self._build_result(
                    RuntimeStatus.FAILED,
                    [ConsistencyIssue("migration_not_at_head", IssueSeverity.FATAL, "schema")],
                    repairs,
                )

            issues = self.run_consistency_checks()
            repairs.extend(self.apply_auto_repairs(issues))
            issues = self.run_consistency_checks()

            fatal = [i for i in issues if i.severity == IssueSeverity.FATAL]
            manual = [i for i in issues if i.severity == IssueSeverity.MANUAL]
            if fatal:
                self._fail_recovery(fatal[0].code)
                return self._build_result(RuntimeStatus.FAILED, issues, repairs)

            self._runtime.transition(RuntimeStatus.SYNCING)

            if not market_data_ready:
                self._runtime.transition(
                    RuntimeStatus.DEGRADED,
                    last_error="market_data_not_ready",
                )
                return self._build_result(RuntimeStatus.DEGRADED, issues, repairs)

            if manual:
                self._runtime.transition(
                    RuntimeStatus.DEGRADED,
                    last_error=manual[0].code,
                )
                return self._build_result(RuntimeStatus.DEGRADED, issues, repairs)

            self._runtime.transition(RuntimeStatus.READY, last_error="")
            self._capture_recovery_snapshot()
            return self._build_result(RuntimeStatus.READY, issues, repairs)
        finally:
            RecoveryService._recovery_active = False

    def _build_result(
        self,
        status: RuntimeStatus,
        issues: list[ConsistencyIssue],
        repairs: list[str],
    ) -> RecoveryResult:
        runtime = self._runtime.get_state()
        entry_ready = (
            status == RuntimeStatus.READY
            and not runtime.paused
            and not runtime.kill_switch
        )
        return RecoveryResult(
            success=status in {RuntimeStatus.READY, RuntimeStatus.DEGRADED},
            final_status=status,
            issues=tuple(issues),
            repairs_applied=tuple(repairs),
            entry_readiness=entry_ready,
        )

    def _fail_recovery(self, code: str) -> None:
        self._runtime.transition(RuntimeStatus.FAILED, last_error=code)
        runtime = self._runtime.get_state()
        self._repo.append_audit_event(
            event_type="RECOVERY_FAILED",
            aggregate_type="runtime_state",
            aggregate_id=runtime.instance_id,
            payload_json={"code": code},
            created_at=self._clock.now(),
        )

    def _capture_recovery_snapshot(self) -> None:
        self._snapshots.capture_snapshot(
            evaluation_time=self._clock.now(),
            event="recovery",
        )

    def _migration_at_head(self) -> bool:
        if self._db_engine is None or self._alembic_config is None:
            return True
        script = ScriptDirectory.from_config(self._alembic_config)
        head = script.get_current_head()
        with self._db_engine.connect() as conn:
            current = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
        return current == head

    def _check_orphan_scheduler_runs(self, issues: list[ConsistencyIssue]) -> None:
        orphans = self._repo.get_running_scheduler_runs()
        for run in orphans:
            issues.append(
                ConsistencyIssue(
                    code="orphan_scheduler_run",
                    severity=IssueSeverity.AUTO_REPAIRABLE,
                    message="Scheduler run stuck in RUNNING",
                    details={"run_id": str(run.run_id), "job_name": run.job_name},
                )
            )

    def _check_stale_heartbeat(self, issues: list[ConsistencyIssue]) -> None:
        runtime = self._repo.get_runtime_state()
        if runtime is None:
            return
        age = self._clock.now() - runtime.heartbeat_at
        if age > timedelta(seconds=self._config.stale_runtime_threshold_seconds):
            issues.append(
                ConsistencyIssue(
                    code="stale_runtime_heartbeat",
                    severity=IssueSeverity.AUTO_REPAIRABLE,
                    message="Runtime heartbeat is stale",
                    details={"age_seconds": int(age.total_seconds())},
                )
            )

    def _check_multiple_open_positions(self, issues: list[ConsistencyIssue]) -> None:
        counts = self._repo.count_open_positions_by_symbol()
        for symbol, count in counts.items():
            if count > 1:
                issues.append(
                    ConsistencyIssue(
                        code="multiple_open_positions",
                        severity=IssueSeverity.FATAL,
                        message=f"Multiple open positions for {symbol}",
                        details={"symbol": symbol, "count": count},
                    )
                )

    def _check_intent_order_fill_chain(self, issues: list[ConsistencyIssue]) -> None:
        for intent in self._repo.list_all_intents():
            order = self._repo.get_order_for_intent(intent.intent_id)
            fills = self._repo.get_fills_for_order(order.paper_order_id) if order else ()

            if intent.status == TradeIntentStatus.FILLED and not fills:
                issues.append(
                    ConsistencyIssue(
                        code="filled_intent_without_fill",
                        severity=IssueSeverity.MANUAL,
                        message="FILLED intent has no fill row",
                        details={"intent_id": str(intent.intent_id)},
                    )
                )
            elif fills and intent.status not in TERMINAL_INTENT_STATUSES:
                issues.append(
                    ConsistencyIssue(
                        code="filled_intent_without_status",
                        severity=IssueSeverity.AUTO_REPAIRABLE,
                        message="Fill exists but intent not terminal",
                        details={"intent_id": str(intent.intent_id)},
                    )
                )

            if order and order.status == PaperOrderStatus.OPEN and fills:
                issues.append(
                    ConsistencyIssue(
                        code="open_order_with_fill",
                        severity=IssueSeverity.AUTO_REPAIRABLE,
                        message="OPEN order has fill rows",
                        details={
                            "paper_order_id": str(order.paper_order_id),
                            "remaining_quantity": "0",
                        },
                    )
                )

            if (
                intent.status in TERMINAL_INTENT_STATUSES
                and intent.status != TradeIntentStatus.FILLED
            ):
                if order is None and intent.status not in {
                    TradeIntentStatus.REJECTED,
                    TradeIntentStatus.CANCELLED,
                }:
                    issues.append(
                        ConsistencyIssue(
                            code="terminal_intent_without_order",
                            severity=IssueSeverity.MANUAL,
                            message="Terminal intent missing order",
                            details={"intent_id": str(intent.intent_id)},
                        )
                    )

    def _check_position_references(self, issues: list[ConsistencyIssue]) -> None:
        for position in self._repo.list_all_positions():
            intent = self._repo.get_intent(position.entry_intent_id)
            if intent is None and position.status != PaperPositionStatus.CLOSED:
                issues.append(
                    ConsistencyIssue(
                        code="position_without_entry_intent",
                        severity=IssueSeverity.FATAL,
                        message="Open position missing entry intent",
                        details={"position_id": str(position.position_id)},
                    )
                )

            order = self._repo.get_order_for_intent(position.entry_intent_id) if intent else None
            fills = self._repo.get_fills_for_order(order.paper_order_id) if order else ()
            open_or_closing = {
                PaperPositionStatus.OPEN,
                PaperPositionStatus.CLOSING,
            }
            if position.status in open_or_closing and not fills:
                issues.append(
                    ConsistencyIssue(
                        code="position_without_entry_fill",
                        severity=IssueSeverity.MANUAL,
                        message="Position missing entry fill",
                        details={"position_id": str(position.position_id)},
                    )
                )

            if position.status == PaperPositionStatus.CLOSING:
                issues.append(
                    ConsistencyIssue(
                        code="closing_position_pending_exit",
                        severity=IssueSeverity.MANUAL,
                        message="CLOSING position requires exit processing",
                        details={"position_id": str(position.position_id)},
                    )
                )

        for fill in self._repo.list_all_fills():
            order_row = self._repo.session.get(PaperOrderRow, fill.paper_order_id)
            if order_row is None:
                issues.append(
                    ConsistencyIssue(
                        code="fill_without_order",
                        severity=IssueSeverity.FATAL,
                        message="Fill references missing order",
                        details={"fill_id": str(fill.fill_id)},
                    )
                )
                continue
            position_for_intent = self._repo.get_open_position_for_symbol(fill.symbol)
            if (
                position_for_intent is None
                and order_row.status == PaperOrderStatus.FILLED.value
            ):
                issues.append(
                    ConsistencyIssue(
                        code="fill_without_position",
                        severity=IssueSeverity.MANUAL,
                        message="Filled order has no open position",
                        details={"fill_id": str(fill.fill_id)},
                    )
                )

    def _check_stop_invariants(self, issues: list[ConsistencyIssue]) -> None:
        for position in self._repo.list_all_positions():
            if position.current_stop < position.initial_stop:
                issues.append(
                    ConsistencyIssue(
                        code="current_stop_below_initial",
                        severity=IssueSeverity.FATAL,
                        message="current_stop < initial_stop",
                        details={"position_id": str(position.position_id)},
                    )
                )
            if position.highest_close_since_entry < position.average_entry_price:
                issues.append(
                    ConsistencyIssue(
                        code="highest_close_below_entry",
                        severity=IssueSeverity.MANUAL,
                        message="highest_close_since_entry below average_entry_price",
                        details={"position_id": str(position.position_id)},
                    )
                )
            events = self._repo.list_stop_events_for_position(position.position_id)
            for event in events:
                if event.new_stop < event.previous_stop:
                    issues.append(
                        ConsistencyIssue(
                            code="invalid_stop_history",
                            severity=IssueSeverity.FATAL,
                            message="Stop history not monotonic",
                            details={"stop_event_id": str(event.stop_event_id)},
                        )
                    )

    def _check_duplicate_fills(self, issues: list[ConsistencyIssue]) -> None:
        seen: dict[str, str] = {}
        for fill in self._repo.list_all_fills():
            key = fill.deterministic_fill_key
            if key in seen:
                issues.append(
                    ConsistencyIssue(
                        code="duplicate_deterministic_fill",
                        severity=IssueSeverity.FATAL,
                        message="Duplicate deterministic fill key",
                        details={"fill_id": str(fill.fill_id), "key": key},
                    )
                )
            seen[key] = str(fill.fill_id)


def recover_on_startup(
    repository: PaperTradingRepository,
    config: PaperTradingConfig,
    advisory_lock: AdvisoryLock,
    *,
    market_data_ready: bool,
    db_engine: Engine | None = None,
    alembic_config: Config | None = None,
    clock: Clock | None = None,
) -> RecoveryResult:
    """Entry point for runtime startup recovery."""
    resolved_clock = clock or SystemClock()
    service = RecoveryService(
        repository,
        config,
        clock=resolved_clock,
        db_engine=db_engine,
        alembic_config=alembic_config,
    )
    result = service.recover_on_startup(advisory_lock, market_data_ready=market_data_ready)
    runtime = repository.get_runtime_state()
    if runtime is not None:
        with _transaction_scope(repository.session):
            repository.append_audit_event(
                event_type="RECOVERY_COMPLETED",
                aggregate_type="runtime_state",
                aggregate_id=runtime.instance_id,
                payload_json={
                    "final_status": result.final_status.value,
                    "repairs": list(result.repairs_applied),
                    "issue_count": len(result.issues),
                },
                created_at=resolved_clock.now(),
            )
    return result
