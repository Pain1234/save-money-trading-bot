"""Transactional repository for paper trading persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from paper_trading.audit import new_audit_event
from paper_trading.db.orm import (
    FAIRNESS_CURSOR_SINGLETON_ID,
    RUNTIME_SINGLETON_ID,
    WALLET_SINGLETON_ID,
    FundingEventRow,
    MarketEventFairnessCursorRow,
    MarketEventGroupStateRow,
    PaperFillRow,
    PaperOrderRow,
    PaperPositionRow,
    PaperWalletRow,
    PortfolioSnapshotRow,
    PositionStopHistoryRow,
    RuntimeStateRow,
    SchedulerRunRow,
    StrategyEvaluationRow,
    TradeIntentRow,
)
from paper_trading.enums import (
    PaperPositionStatus,
    RuntimeStatus,
    SchedulerRunStatus,
    TradeIntentStatus,
)
from paper_trading.event_fairness import MarketEventGroupState
from paper_trading.ids import scheduler_run_key
from paper_trading.mappers import (
    audit_row_to_domain,
    evaluation_row_to_domain,
    fill_row_to_domain,
    funding_row_to_domain,
    intent_row_to_domain,
    order_row_to_domain,
    position_row_to_domain,
    runtime_row_to_domain,
    scheduler_row_to_domain,
    snapshot_row_to_domain,
    stop_event_row_to_domain,
    wallet_row_to_domain,
)
from paper_trading.market_event_errors import is_retryable_market_event_error
from paper_trading.models import (
    AuditEvent,
    FundingEventRecord,
    PaperFill,
    PaperOrder,
    PaperPosition,
    PaperWalletState,
    PortfolioSnapshot,
    PositionStopEvent,
    RuntimeState,
    SchedulerRun,
    StrategyEvaluationRecord,
    TradeIntent,
)
from paper_trading.transitions import TERMINAL_INTENT_STATUSES

NONTERMINAL_INTENT_STATUS_VALUES: tuple[str, ...] = tuple(
    s.value for s in TradeIntentStatus if s not in TERMINAL_INTENT_STATUSES
)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class PaperTradingRepository:
    """PostgreSQL repository with idempotent inserts and explicit transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._active_soak_run_id: UUID | None = None

    @property
    def session(self) -> Session:
        return self._session

    def set_active_soak_run_id(self, soak_run_id: UUID | None) -> None:
        self._active_soak_run_id = soak_run_id

    def get_runtime_state(self) -> RuntimeState | None:
        row = self._session.get(RuntimeStateRow, RUNTIME_SINGLETON_ID)
        return runtime_row_to_domain(row) if row else None

    def get_runtime_state_for_update(self) -> RuntimeState | None:
        """Lock the singleton so control changes serialize with new-risk writes."""
        row = self._session.execute(
            select(RuntimeStateRow)
            .where(RuntimeStateRow.instance_id == RUNTIME_SINGLETON_ID)
            .with_for_update()
        ).scalar_one_or_none()
        return runtime_row_to_domain(row) if row else None

    def update_runtime_state(
        self,
        *,
        status: RuntimeStatus | None = None,
        last_error: str | None = None,
        started_at: datetime | None = None,
        heartbeat_at: datetime | None = None,
        kill_switch: bool | None = None,
        paused: bool | None = None,
        current_cycle_id: UUID | None = None,
        expected_version: int | None = None,
    ) -> RuntimeState:
        row = self._session.get(RuntimeStateRow, RUNTIME_SINGLETON_ID)
        if row is None:
            raise LookupError("runtime_state singleton not seeded")
        if expected_version is not None and row.version != expected_version:
            raise ValueError("runtime_state version conflict")
        if status is not None:
            row.status = status.value
        if last_error is not None:
            row.last_error = last_error
        if started_at is not None:
            row.started_at = started_at
        if heartbeat_at is not None:
            row.heartbeat_at = heartbeat_at
        if kill_switch is not None:
            row.kill_switch = kill_switch
        if paused is not None:
            row.paused = paused
        if current_cycle_id is not None:
            row.current_cycle_id = current_cycle_id
        row.version += 1
        self._session.flush()
        return runtime_row_to_domain(row)

    def get_wallet(self) -> PaperWalletState | None:
        row = self._session.get(PaperWalletRow, WALLET_SINGLETON_ID)
        return wallet_row_to_domain(row) if row else None

    def update_wallet(
        self,
        *,
        cash_delta: Decimal = Decimal("0"),
        realized_pnl_delta: Decimal = Decimal("0"),
        fees_delta: Decimal = Decimal("0"),
        funding_delta: Decimal = Decimal("0"),
        slippage_delta: Decimal = Decimal("0"),
        expected_version: int | None = None,
        updated_at: datetime | None = None,
    ) -> PaperWalletState:
        row = self._session.get(PaperWalletRow, WALLET_SINGLETON_ID)
        if row is None:
            raise LookupError("paper_wallet singleton not seeded")
        if expected_version is not None and row.version != expected_version:
            raise ValueError("paper_wallet version conflict")
        row.cash += cash_delta
        row.total_realized_pnl += realized_pnl_delta
        row.total_fees += fees_delta
        row.total_funding += funding_delta
        row.total_slippage += slippage_delta
        row.updated_at = updated_at or _utc_now()
        row.version += 1
        self._session.flush()
        return wallet_row_to_domain(row)

    def insert_or_get_strategy_evaluation(
        self, row: StrategyEvaluationRow
    ) -> tuple[StrategyEvaluationRecord, bool]:
        stmt = (
            pg_insert(StrategyEvaluationRow)
            .values(
                evaluation_id=row.evaluation_id,
                symbol=row.symbol,
                evaluation_time=row.evaluation_time,
                daily_candle_open_time=row.daily_candle_open_time,
                weekly_candle_key=row.weekly_candle_key,
                monthly_candle_key=row.monthly_candle_key,
                daily_candle_key=row.daily_candle_key,
                strategy_version=row.strategy_version,
                regime_result=row.regime_result,
                entry_result=row.entry_result,
                rejection_reasons=row.rejection_reasons,
                deterministic_input_hash=row.deterministic_input_hash,
                created_at=row.created_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    StrategyEvaluationRow.strategy_version,
                    StrategyEvaluationRow.symbol,
                    StrategyEvaluationRow.daily_candle_open_time,
                ]
            )
            .returning(StrategyEvaluationRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return evaluation_row_to_domain(inserted), True
        existing = self._session.execute(
            select(StrategyEvaluationRow).where(
                StrategyEvaluationRow.strategy_version == row.strategy_version,
                StrategyEvaluationRow.symbol == row.symbol,
                StrategyEvaluationRow.daily_candle_open_time == row.daily_candle_open_time,
            )
        ).scalar_one()
        return evaluation_row_to_domain(existing), False

    def insert_or_get_trade_intent(self, row: TradeIntentRow) -> tuple[TradeIntent, bool]:
        stmt = (
            pg_insert(TradeIntentRow)
            .values(
                intent_id=row.intent_id,
                idempotency_key=row.idempotency_key,
                symbol=row.symbol,
                side=row.side,
                signal_type=row.signal_type,
                signal_time=row.signal_time,
                scheduled_fill_time=row.scheduled_fill_time,
                requested_entry=row.requested_entry,
                requested_stop=row.requested_stop,
                requested_quantity=row.requested_quantity,
                approved_quantity=row.approved_quantity,
                risk_amount=row.risk_amount,
                status=row.status,
                strategy_evaluation_id=row.strategy_evaluation_id,
                rejection_reason=row.rejection_reason,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    TradeIntentRow.strategy_evaluation_id,
                    TradeIntentRow.symbol,
                    TradeIntentRow.side,
                    TradeIntentRow.signal_type,
                ]
            )
            .returning(TradeIntentRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return intent_row_to_domain(inserted), True
        existing = self._session.execute(
            select(TradeIntentRow).where(
                TradeIntentRow.strategy_evaluation_id == row.strategy_evaluation_id,
                TradeIntentRow.symbol == row.symbol,
                TradeIntentRow.side == row.side,
                TradeIntentRow.signal_type == row.signal_type,
            )
        ).scalar_one()
        return intent_row_to_domain(existing), False

    def insert_or_get_paper_order(self, row: PaperOrderRow) -> tuple[PaperOrder, bool]:
        stmt = (
            pg_insert(PaperOrderRow)
            .values(
                paper_order_id=row.paper_order_id,
                intent_id=row.intent_id,
                symbol=row.symbol,
                side=row.side,
                order_type=row.order_type,
                requested_quantity=row.requested_quantity,
                remaining_quantity=row.remaining_quantity,
                expected_fill_time=row.expected_fill_time,
                status=row.status,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[PaperOrderRow.intent_id])
            .returning(PaperOrderRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return order_row_to_domain(inserted), True
        existing = self._session.execute(
            select(PaperOrderRow).where(PaperOrderRow.intent_id == row.intent_id)
        ).scalar_one()
        return order_row_to_domain(existing), False

    def insert_or_get_paper_fill(self, row: PaperFillRow) -> tuple[PaperFill, bool]:
        fill_kind = row.fill_kind or "ENTRY"
        if row.paper_order_id is not None:
            existing_entry = self._session.execute(
                select(PaperFillRow).where(
                    PaperFillRow.paper_order_id == row.paper_order_id,
                    PaperFillRow.candle_key == row.candle_key,
                    PaperFillRow.fill_sequence == row.fill_sequence,
                )
            ).scalar_one_or_none()
            if existing_entry is not None:
                return fill_row_to_domain(existing_entry), False
        if row.position_id is not None and fill_kind == "EXIT":
            existing_exit = self._session.execute(
                select(PaperFillRow).where(
                    PaperFillRow.position_id == row.position_id,
                    PaperFillRow.candle_key == row.candle_key,
                    PaperFillRow.fill_sequence == row.fill_sequence,
                    PaperFillRow.fill_kind == "EXIT",
                )
            ).scalar_one_or_none()
            if existing_exit is not None:
                return fill_row_to_domain(existing_exit), False

        stmt = (
            pg_insert(PaperFillRow)
            .values(
                fill_id=row.fill_id,
                paper_order_id=row.paper_order_id,
                position_id=row.position_id,
                fill_kind=fill_kind,
                symbol=row.symbol,
                side=row.side,
                quantity=row.quantity,
                market_open_price=row.market_open_price,
                slippage=row.slippage,
                fill_price=row.fill_price,
                fee=row.fee,
                fill_time=row.fill_time,
                candle_key=row.candle_key,
                fill_sequence=row.fill_sequence,
                deterministic_fill_key=row.deterministic_fill_key,
            )
            .on_conflict_do_nothing(index_elements=[PaperFillRow.deterministic_fill_key])
            .returning(PaperFillRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return fill_row_to_domain(inserted), True
        existing = self._session.execute(
            select(PaperFillRow).where(
                PaperFillRow.deterministic_fill_key == row.deterministic_fill_key
            )
        ).scalar_one()
        return fill_row_to_domain(existing), False

    def insert_or_get_stop_event(
        self, row: PositionStopHistoryRow
    ) -> tuple[PositionStopEvent, bool]:
        stmt = (
            pg_insert(PositionStopHistoryRow)
            .values(
                stop_event_id=row.stop_event_id,
                position_id=row.position_id,
                previous_stop=row.previous_stop,
                new_stop=row.new_stop,
                highest_close=row.highest_close,
                atr=row.atr,
                evaluation_time=row.evaluation_time,
                reason=row.reason,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    PositionStopHistoryRow.position_id,
                    PositionStopHistoryRow.evaluation_time,
                ]
            )
            .returning(PositionStopHistoryRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return stop_event_row_to_domain(inserted), True
        existing = self._session.execute(
            select(PositionStopHistoryRow).where(
                PositionStopHistoryRow.position_id == row.position_id,
                PositionStopHistoryRow.evaluation_time == row.evaluation_time,
            )
        ).scalar_one()
        return stop_event_row_to_domain(existing), False

    def insert_or_get_funding_event(
        self, row: FundingEventRow
    ) -> tuple[FundingEventRecord, bool]:
        stmt = (
            pg_insert(FundingEventRow)
            .values(
                funding_event_id=row.funding_event_id,
                position_id=row.position_id,
                symbol=row.symbol,
                funding_rate=row.funding_rate,
                notional=row.notional,
                amount=row.amount,
                funding_time=row.funding_time,
                deterministic_key=row.deterministic_key,
            )
            .on_conflict_do_nothing(
                index_elements=[FundingEventRow.position_id, FundingEventRow.funding_time]
            )
            .returning(FundingEventRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return funding_row_to_domain(inserted), True
        existing = self._session.execute(
            select(FundingEventRow).where(
                FundingEventRow.position_id == row.position_id,
                FundingEventRow.funding_time == row.funding_time,
            )
        ).scalar_one()
        return funding_row_to_domain(existing), False

    def insert_or_get_scheduler_run(self, row: SchedulerRunRow) -> tuple[SchedulerRun, bool]:
        soak_run_id = (
            row.soak_run_id if row.soak_run_id is not None else self._active_soak_run_id
        )
        stmt = (
            pg_insert(SchedulerRunRow)
            .values(
                run_id=row.run_id,
                job_name=row.job_name,
                scheduled_for=row.scheduled_for,
                started_at=row.started_at,
                completed_at=row.completed_at,
                status=row.status,
                error=row.error,
                idempotency_key=row.idempotency_key,
                recovery_of_run_id=row.recovery_of_run_id,
                resolved_by_run_id=row.resolved_by_run_id,
                soak_run_id=soak_run_id,
            )
            .on_conflict_do_nothing(
                index_elements=[SchedulerRunRow.job_name, SchedulerRunRow.scheduled_for]
            )
            .returning(SchedulerRunRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return scheduler_row_to_domain(inserted), True
        existing = self._session.execute(
            select(SchedulerRunRow).where(
                SchedulerRunRow.job_name == row.job_name,
                SchedulerRunRow.scheduled_for == row.scheduled_for,
            )
        ).scalar_one()
        return scheduler_row_to_domain(existing), False

    def create_position(self, row: PaperPositionRow) -> PaperPosition:
        self._session.add(row)
        self._session.flush()
        return position_row_to_domain(row)

    def update_position(self, row: PaperPositionRow) -> PaperPosition:
        self._session.merge(row)
        self._session.flush()
        merged = self._session.get(PaperPositionRow, row.position_id)
        assert merged is not None
        return position_row_to_domain(merged)

    def get_open_positions(self) -> tuple[PaperPosition, ...]:
        rows = self._session.execute(
            select(PaperPositionRow).where(
                PaperPositionRow.status.in_(
                    [PaperPositionStatus.OPEN.value, PaperPositionStatus.CLOSING.value]
                )
            )
        ).scalars()
        return tuple(position_row_to_domain(r) for r in rows)

    def get_nonterminal_intent_for_symbol(self, symbol: str) -> TradeIntent | None:
        row = self._session.execute(
            select(TradeIntentRow).where(
                TradeIntentRow.symbol == symbol,
                TradeIntentRow.status.in_(NONTERMINAL_INTENT_STATUS_VALUES),
            )
        ).scalar_one_or_none()
        return intent_row_to_domain(row) if row else None

    def get_scheduled_intents_for_symbol(
        self,
        symbol: str,
        scheduled_fill_time: datetime,
    ) -> tuple[TradeIntent, ...]:
        rows = self._session.execute(
            select(TradeIntentRow)
            .where(
                TradeIntentRow.symbol == symbol,
                TradeIntentRow.scheduled_fill_time == scheduled_fill_time,
                TradeIntentRow.status.in_(
                    [
                        TradeIntentStatus.SCHEDULED.value,
                        TradeIntentStatus.SUBMITTED_TO_PAPER_ENGINE.value,
                    ]
                ),
            )
            .order_by(TradeIntentRow.created_at)
        ).scalars()
        return tuple(intent_row_to_domain(r) for r in rows)

    def get_open_position_for_symbol(self, symbol: str) -> PaperPosition | None:
        row = self._session.execute(
            select(PaperPositionRow).where(
                PaperPositionRow.symbol == symbol,
                PaperPositionRow.status.in_(
                    [PaperPositionStatus.OPEN.value, PaperPositionStatus.CLOSING.value]
                ),
            )
        ).scalar_one_or_none()
        return position_row_to_domain(row) if row else None

    def insert_or_get_portfolio_snapshot(
        self, row: PortfolioSnapshotRow
    ) -> tuple[PortfolioSnapshot, bool]:
        stmt = (
            pg_insert(PortfolioSnapshotRow)
            .values(
                snapshot_id=row.snapshot_id,
                evaluation_time=row.evaluation_time,
                cash=row.cash,
                margin_used=row.margin_used,
                equity=row.equity,
                unrealized_pnl=row.unrealized_pnl,
                realized_pnl=row.realized_pnl,
                total_open_risk=row.total_open_risk,
                open_position_count=row.open_position_count,
                idempotency_key=row.idempotency_key,
            )
            .on_conflict_do_nothing(index_elements=[PortfolioSnapshotRow.idempotency_key])
            .returning(PortfolioSnapshotRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return snapshot_row_to_domain(inserted), True
        existing = self._session.execute(
            select(PortfolioSnapshotRow).where(
                PortfolioSnapshotRow.idempotency_key == row.idempotency_key
            )
        ).scalar_one()
        return snapshot_row_to_domain(existing), False

    def get_scheduler_run(self, job_name: str, scheduled_for: datetime) -> SchedulerRun | None:
        row = self._session.execute(
            select(SchedulerRunRow).where(
                SchedulerRunRow.job_name == job_name,
                SchedulerRunRow.scheduled_for == scheduled_for,
            )
        ).scalar_one_or_none()
        return scheduler_row_to_domain(row) if row else None

    def complete_scheduler_run(
        self,
        *,
        job_name: str,
        scheduled_for: datetime,
        status: SchedulerRunStatus,
        completed_at: datetime,
        error: str | None = None,
    ) -> SchedulerRun:
        self._session.execute(
            update(SchedulerRunRow)
            .where(
                SchedulerRunRow.job_name == job_name,
                SchedulerRunRow.scheduled_for == scheduled_for,
            )
            .values(
                status=status.value,
                completed_at=completed_at,
                error=error,
            )
        )
        row = self._session.execute(
            select(SchedulerRunRow).where(
                SchedulerRunRow.job_name == job_name,
                SchedulerRunRow.scheduled_for == scheduled_for,
            )
        ).scalar_one()
        self._session.flush()
        return scheduler_row_to_domain(row)

    def list_permanent_configuration_failures(self) -> tuple[SchedulerRun, ...]:
        from paper_trading.market_event_errors import PERMANENT_CONFIGURATION_ERROR_CODES

        rows = self._session.execute(
            select(SchedulerRunRow).where(
                SchedulerRunRow.status == SchedulerRunStatus.FAILED.value,
                SchedulerRunRow.job_name.like("me:%"),
                SchedulerRunRow.error.in_(tuple(PERMANENT_CONFIGURATION_ERROR_CODES)),
                SchedulerRunRow.recovery_of_run_id.is_(None),
                SchedulerRunRow.resolved_by_run_id.is_(None),
                ~SchedulerRunRow.job_name.like("%:recovery:%"),
            )
        ).scalars()
        return tuple(scheduler_row_to_domain(row) for row in rows)

    def count_recovery_attempts(self, original_run_id: UUID) -> int:
        count = self._session.execute(
            select(SchedulerRunRow.run_id).where(
                SchedulerRunRow.recovery_of_run_id == original_run_id
            )
        ).all()
        return len(count)

    def get_active_recovery_attempt(self, original_run_id: UUID) -> SchedulerRun | None:
        rows = self._session.execute(
            select(SchedulerRunRow)
            .where(
                SchedulerRunRow.recovery_of_run_id == original_run_id,
            )
            .order_by(SchedulerRunRow.started_at.desc())
        ).scalars()
        for row in rows:
            if row.status == SchedulerRunStatus.RUNNING.value:
                return scheduler_row_to_domain(row)
            if (
                row.status == SchedulerRunStatus.SKIPPED.value
                and is_retryable_market_event_error(row.error)
            ):
                return scheduler_row_to_domain(row)
        return None

    def reactivate_scheduler_run(
        self,
        *,
        job_name: str,
        scheduled_for: datetime,
        started_at: datetime,
    ) -> None:
        self._session.execute(
            update(SchedulerRunRow)
            .where(
                SchedulerRunRow.job_name == job_name,
                SchedulerRunRow.scheduled_for == scheduled_for,
            )
            .values(
                status=SchedulerRunStatus.RUNNING.value,
                error=None,
                started_at=started_at,
                completed_at=None,
            )
        )
        self._session.flush()

    def create_recovery_attempt(
        self,
        *,
        original_run: SchedulerRun,
        recovery_job_name: str,
        started_at: datetime,
    ) -> tuple[SchedulerRun, bool]:
        row = SchedulerRunRow(
            run_id=uuid4(),
            job_name=recovery_job_name,
            scheduled_for=original_run.scheduled_for,
            started_at=started_at,
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key=scheduler_run_key(recovery_job_name, original_run.scheduled_for),
            recovery_of_run_id=original_run.run_id,
        )
        return self.insert_or_get_scheduler_run(row)

    def mark_run_resolved(
        self,
        *,
        original_run_id: UUID,
        recovery_run_id: UUID,
    ) -> None:
        self._session.execute(
            update(SchedulerRunRow)
            .where(
                SchedulerRunRow.run_id == original_run_id,
                SchedulerRunRow.resolved_by_run_id.is_(None),
            )
            .values(resolved_by_run_id=recovery_run_id)
        )
        self._session.flush()

    def delete_scheduler_run_if_running(
        self,
        *,
        job_name: str,
        scheduled_for: datetime,
    ) -> bool:
        result = self._session.execute(
            delete(SchedulerRunRow).where(
                SchedulerRunRow.job_name == job_name,
                SchedulerRunRow.scheduled_for == scheduled_for,
                SchedulerRunRow.status == SchedulerRunStatus.RUNNING.value,
                SchedulerRunRow.completed_at.is_(None),
            )
        )
        self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    def get_running_scheduler_runs(self) -> tuple[SchedulerRun, ...]:
        rows = self._session.execute(
            select(SchedulerRunRow).where(
                SchedulerRunRow.status == SchedulerRunStatus.RUNNING.value
            )
        ).scalars()
        return tuple(scheduler_row_to_domain(r) for r in rows)

    def list_scheduler_runs(
        self,
        *,
        limit: int,
        after_scheduled_for: datetime | None = None,
        after_run_id: UUID | None = None,
    ) -> tuple[SchedulerRun, ...]:
        stmt = select(SchedulerRunRow).order_by(
            SchedulerRunRow.scheduled_for.desc(),
            SchedulerRunRow.run_id.desc(),
        )
        if after_scheduled_for is not None and after_run_id is not None:
            stmt = stmt.where(
                (SchedulerRunRow.scheduled_for < after_scheduled_for)
                | (
                    (SchedulerRunRow.scheduled_for == after_scheduled_for)
                    & (SchedulerRunRow.run_id < after_run_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(scheduler_row_to_domain(r) for r in rows)

    def list_audit_events(
        self,
        *,
        limit: int,
        after_created_at: datetime | None = None,
        after_event_id: UUID | None = None,
    ) -> tuple[AuditEvent, ...]:
        from paper_trading.db.orm import AuditEventRow

        stmt = select(AuditEventRow).order_by(
            AuditEventRow.created_at.desc(),
            AuditEventRow.event_id.desc(),
        )
        if after_created_at is not None and after_event_id is not None:
            stmt = stmt.where(
                (AuditEventRow.created_at < after_created_at)
                | (
                    (AuditEventRow.created_at == after_created_at)
                    & (AuditEventRow.event_id < after_event_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(audit_row_to_domain(r) for r in rows)

    def list_evaluations(
        self,
        *,
        limit: int,
        after_created_at: datetime | None = None,
        after_evaluation_id: UUID | None = None,
    ) -> tuple[StrategyEvaluationRecord, ...]:
        stmt = select(StrategyEvaluationRow).order_by(
            StrategyEvaluationRow.created_at.desc(),
            StrategyEvaluationRow.evaluation_id.desc(),
        )
        if after_created_at is not None and after_evaluation_id is not None:
            stmt = stmt.where(
                (StrategyEvaluationRow.created_at < after_created_at)
                | (
                    (StrategyEvaluationRow.created_at == after_created_at)
                    & (StrategyEvaluationRow.evaluation_id < after_evaluation_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(evaluation_row_to_domain(r) for r in rows)

    def list_intents(
        self,
        *,
        limit: int,
        after_created_at: datetime | None = None,
        after_intent_id: UUID | None = None,
    ) -> tuple[TradeIntent, ...]:
        stmt = select(TradeIntentRow).order_by(
            TradeIntentRow.created_at.desc(),
            TradeIntentRow.intent_id.desc(),
        )
        if after_created_at is not None and after_intent_id is not None:
            stmt = stmt.where(
                (TradeIntentRow.created_at < after_created_at)
                | (
                    (TradeIntentRow.created_at == after_created_at)
                    & (TradeIntentRow.intent_id < after_intent_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(intent_row_to_domain(r) for r in rows)

    def list_orders(
        self,
        *,
        limit: int,
        after_created_at: datetime | None = None,
        after_order_id: UUID | None = None,
    ) -> tuple[PaperOrder, ...]:
        stmt = select(PaperOrderRow).order_by(
            PaperOrderRow.created_at.desc(),
            PaperOrderRow.paper_order_id.desc(),
        )
        if after_created_at is not None and after_order_id is not None:
            stmt = stmt.where(
                (PaperOrderRow.created_at < after_created_at)
                | (
                    (PaperOrderRow.created_at == after_created_at)
                    & (PaperOrderRow.paper_order_id < after_order_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(order_row_to_domain(r) for r in rows)

    def list_fills(
        self,
        *,
        limit: int,
        after_fill_time: datetime | None = None,
        after_fill_id: UUID | None = None,
    ) -> tuple[PaperFill, ...]:
        stmt = select(PaperFillRow).order_by(
            PaperFillRow.fill_time.desc(),
            PaperFillRow.fill_id.desc(),
        )
        if after_fill_time is not None and after_fill_id is not None:
            stmt = stmt.where(
                (PaperFillRow.fill_time < after_fill_time)
                | (
                    (PaperFillRow.fill_time == after_fill_time)
                    & (PaperFillRow.fill_id < after_fill_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(fill_row_to_domain(r) for r in rows)

    def list_positions(
        self,
        *,
        limit: int,
        after_opened_at: datetime | None = None,
        after_position_id: UUID | None = None,
        status: str | None = None,
        open_only: bool = False,
    ) -> tuple[PaperPosition, ...]:
        stmt = select(PaperPositionRow).order_by(
            PaperPositionRow.opened_at.desc(),
            PaperPositionRow.position_id.desc(),
        )
        if open_only:
            stmt = stmt.where(
                PaperPositionRow.status.in_(
                    [
                        PaperPositionStatus.OPEN.value,
                        PaperPositionStatus.CLOSING.value,
                    ]
                )
            )
        elif status is not None:
            stmt = stmt.where(PaperPositionRow.status == status)
        if after_opened_at is not None and after_position_id is not None:
            stmt = stmt.where(
                (PaperPositionRow.opened_at < after_opened_at)
                | (
                    (PaperPositionRow.opened_at == after_opened_at)
                    & (PaperPositionRow.position_id < after_position_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(position_row_to_domain(r) for r in rows)

    def get_position(self, position_id: UUID) -> PaperPosition | None:
        row = self._session.get(PaperPositionRow, position_id)
        return position_row_to_domain(row) if row else None

    def get_order_for_intent(self, intent_id: UUID) -> PaperOrder | None:
        row = self._session.execute(
            select(PaperOrderRow).where(PaperOrderRow.intent_id == intent_id)
        ).scalar_one_or_none()
        return order_row_to_domain(row) if row else None

    def get_fills_for_order(self, paper_order_id: UUID) -> tuple[PaperFill, ...]:
        rows = self._session.execute(
            select(PaperFillRow)
            .where(PaperFillRow.paper_order_id == paper_order_id)
            .order_by(PaperFillRow.fill_sequence)
        ).scalars()
        return tuple(fill_row_to_domain(r) for r in rows)

    def get_intent(self, intent_id: UUID) -> TradeIntent | None:
        row = self._session.get(TradeIntentRow, intent_id)
        return intent_row_to_domain(row) if row else None

    def list_all_fills(self) -> tuple[PaperFill, ...]:
        rows = self._session.execute(select(PaperFillRow)).scalars()
        return tuple(fill_row_to_domain(r) for r in rows)

    def list_all_positions(self) -> tuple[PaperPosition, ...]:
        rows = self._session.execute(select(PaperPositionRow)).scalars()
        return tuple(position_row_to_domain(r) for r in rows)

    def list_all_intents(self) -> tuple[TradeIntent, ...]:
        rows = self._session.execute(select(TradeIntentRow)).scalars()
        return tuple(intent_row_to_domain(r) for r in rows)

    def list_all_orders(self) -> tuple[PaperOrder, ...]:
        rows = self._session.execute(select(PaperOrderRow)).scalars()
        return tuple(order_row_to_domain(r) for r in rows)

    def list_stop_events_for_position(
        self, position_id: UUID
    ) -> tuple[PositionStopEvent, ...]:
        rows = self._session.execute(
            select(PositionStopHistoryRow)
            .where(PositionStopHistoryRow.position_id == position_id)
            .order_by(PositionStopHistoryRow.evaluation_time)
        ).scalars()
        return tuple(stop_event_row_to_domain(r) for r in rows)

    def list_stop_events(
        self,
        *,
        limit: int,
        after_evaluation_time: datetime | None = None,
        after_stop_event_id: UUID | None = None,
    ) -> tuple[PositionStopEvent, ...]:
        stmt = select(PositionStopHistoryRow).order_by(
            PositionStopHistoryRow.evaluation_time.desc(),
            PositionStopHistoryRow.stop_event_id.desc(),
        )
        if after_evaluation_time is not None and after_stop_event_id is not None:
            stmt = stmt.where(
                (PositionStopHistoryRow.evaluation_time < after_evaluation_time)
                | (
                    (PositionStopHistoryRow.evaluation_time == after_evaluation_time)
                    & (PositionStopHistoryRow.stop_event_id < after_stop_event_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(stop_event_row_to_domain(r) for r in rows)

    def list_portfolio_snapshots(
        self,
        *,
        limit: int,
        after_evaluation_time: datetime | None = None,
        after_snapshot_id: UUID | None = None,
    ) -> tuple[PortfolioSnapshot, ...]:
        stmt = select(PortfolioSnapshotRow).order_by(
            PortfolioSnapshotRow.evaluation_time.desc(),
            PortfolioSnapshotRow.snapshot_id.desc(),
        )
        if after_evaluation_time is not None and after_snapshot_id is not None:
            stmt = stmt.where(
                (PortfolioSnapshotRow.evaluation_time < after_evaluation_time)
                | (
                    (PortfolioSnapshotRow.evaluation_time == after_evaluation_time)
                    & (PortfolioSnapshotRow.snapshot_id < after_snapshot_id)
                )
            )
        rows = self._session.execute(stmt.limit(limit)).scalars()
        return tuple(snapshot_row_to_domain(r) for r in rows)

    def update_order_status(
        self,
        paper_order_id: UUID,
        status: str,
        *,
        remaining_quantity: Decimal | None = None,
        updated_at: datetime | None = None,
    ) -> PaperOrder:
        values: dict[str, Any] = {
            "status": status,
            "updated_at": updated_at or _utc_now(),
        }
        if remaining_quantity is not None:
            values["remaining_quantity"] = remaining_quantity
        self._session.execute(
            update(PaperOrderRow)
            .where(PaperOrderRow.paper_order_id == paper_order_id)
            .values(**values)
        )
        row = self._session.get(PaperOrderRow, paper_order_id)
        assert row is not None
        return order_row_to_domain(row)

    def fail_orphan_scheduler_runs(self, *, completed_at: datetime) -> int:
        result = self._session.execute(
            update(SchedulerRunRow)
            .where(SchedulerRunRow.status == SchedulerRunStatus.RUNNING.value)
            .values(
                status=SchedulerRunStatus.FAILED.value,
                completed_at=completed_at,
                error="orphan_run_marked_failed_on_recovery",
            )
        )
        self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)

    def get_latest_portfolio_snapshot(self) -> PortfolioSnapshot | None:
        row = self._session.execute(
            select(PortfolioSnapshotRow)
            .order_by(PortfolioSnapshotRow.evaluation_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        return snapshot_row_to_domain(row) if row else None

    def count_open_positions_by_symbol(self) -> dict[str, int]:
        rows = self._session.execute(
            select(PaperPositionRow.symbol, PaperPositionRow.position_id).where(
                PaperPositionRow.status.in_(
                    [PaperPositionStatus.OPEN.value, PaperPositionStatus.CLOSING.value]
                )
            )
        ).all()
        counts: dict[str, int] = {}
        for symbol, _ in rows:
            counts[symbol] = counts.get(symbol, 0) + 1
        return counts

    def create_portfolio_snapshot(self, row: PortfolioSnapshotRow) -> PortfolioSnapshot:
        self._session.add(row)
        self._session.flush()
        return snapshot_row_to_domain(row)

    def append_audit_event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        payload_json: dict[str, Any],
        cycle_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> AuditEvent:
        row = new_audit_event(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload_json=payload_json,
            cycle_id=cycle_id,
            created_at=created_at,
        )
        self._session.add(row)
        self._session.flush()
        return audit_row_to_domain(row)

    def update_intent_status(
        self,
        intent_id: UUID,
        status: str,
        *,
        approved_quantity: Decimal | None = None,
        rejection_reason: dict[str, Any] | None = None,
        updated_at: datetime | None = None,
    ) -> TradeIntent:
        values: dict[str, Any] = {
            "status": status,
            "updated_at": updated_at or _utc_now(),
        }
        if approved_quantity is not None:
            values["approved_quantity"] = approved_quantity
        if rejection_reason is not None:
            values["rejection_reason"] = rejection_reason
        self._session.execute(
            update(TradeIntentRow).where(TradeIntentRow.intent_id == intent_id).values(**values)
        )
        row = self._session.get(TradeIntentRow, intent_id)
        assert row is not None
        return intent_row_to_domain(row)

    def new_evaluation_row(self, **kwargs: Any) -> StrategyEvaluationRow:
        return StrategyEvaluationRow(evaluation_id=uuid4(), **kwargs)

    def new_intent_row(self, **kwargs: Any) -> TradeIntentRow:
        return TradeIntentRow(intent_id=uuid4(), **kwargs)

    def new_order_row(self, **kwargs: Any) -> PaperOrderRow:
        return PaperOrderRow(paper_order_id=uuid4(), **kwargs)

    def new_fill_row(self, **kwargs: Any) -> PaperFillRow:
        kwargs.setdefault("fill_kind", "ENTRY")
        return PaperFillRow(fill_id=uuid4(), **kwargs)

    def new_position_row(self, **kwargs: Any) -> PaperPositionRow:
        return PaperPositionRow(position_id=uuid4(), **kwargs)

    def get_fairness_group_rotation_cursor(self) -> int:
        row = self._session.get(MarketEventFairnessCursorRow, FAIRNESS_CURSOR_SINGLETON_ID)
        if row is None:
            return 0
        return int(row.group_rotation_cursor)

    def set_fairness_group_rotation_cursor(
        self,
        *,
        cursor: int,
        updated_at: datetime,
    ) -> None:
        row = self._session.get(MarketEventFairnessCursorRow, FAIRNESS_CURSOR_SINGLETON_ID)
        if row is None:
            self._session.add(
                MarketEventFairnessCursorRow(
                    cursor_id=FAIRNESS_CURSOR_SINGLETON_ID,
                    group_rotation_cursor=cursor,
                    updated_at=updated_at,
                )
            )
        else:
            row.group_rotation_cursor = cursor
            row.updated_at = updated_at
        self._session.flush()

    def list_market_event_group_states(self) -> dict[str, MarketEventGroupState]:
        rows = self._session.execute(select(MarketEventGroupStateRow)).scalars()
        return {
            row.group_key: MarketEventGroupState(
                group_key=row.group_key,
                event_type=row.event_type,
                group_time=row.group_time,
                next_attempt_at=row.next_attempt_at,
                defer_count=row.defer_count,
            )
            for row in rows
        }

    def upsert_market_event_group_deferred(
        self,
        *,
        group_key: str,
        event_type: str,
        group_time: datetime,
        next_attempt_at: datetime,
        defer_count: int,
        updated_at: datetime,
    ) -> None:
        existing = self._session.get(MarketEventGroupStateRow, group_key)
        if existing is None:
            self._session.add(
                MarketEventGroupStateRow(
                    group_key=group_key,
                    event_type=event_type,
                    group_time=group_time,
                    next_attempt_at=next_attempt_at,
                    defer_count=defer_count,
                    updated_at=updated_at,
                )
            )
        else:
            existing.event_type = event_type
            existing.group_time = group_time
            existing.next_attempt_at = next_attempt_at
            existing.defer_count = defer_count
            existing.updated_at = updated_at
        self._session.flush()

    def delete_market_event_group_state(self, group_key: str) -> None:
        row = self._session.get(MarketEventGroupStateRow, group_key)
        if row is not None:
            self._session.delete(row)
            self._session.flush()
