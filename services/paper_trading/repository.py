"""Transactional repository for paper trading persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from paper_trading.audit import new_audit_event
from paper_trading.db.orm import (
    RUNTIME_SINGLETON_ID,
    WALLET_SINGLETON_ID,
    FundingEventRow,
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
from paper_trading.enums import PaperPositionStatus, RuntimeStatus
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


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class PaperTradingRepository:
    """PostgreSQL repository with idempotent inserts and explicit transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get_runtime_state(self) -> RuntimeState | None:
        row = self._session.get(RuntimeStateRow, RUNTIME_SINGLETON_ID)
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
        stmt = (
            pg_insert(PaperFillRow)
            .values(
                fill_id=row.fill_id,
                paper_order_id=row.paper_order_id,
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
            .on_conflict_do_nothing(
                index_elements=[
                    PaperFillRow.paper_order_id,
                    PaperFillRow.candle_key,
                    PaperFillRow.fill_sequence,
                ]
            )
            .returning(PaperFillRow)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return fill_row_to_domain(inserted), True
        existing = self._session.execute(
            select(PaperFillRow).where(
                PaperFillRow.paper_order_id == row.paper_order_id,
                PaperFillRow.candle_key == row.candle_key,
                PaperFillRow.fill_sequence == row.fill_sequence,
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
        return PaperFillRow(fill_id=uuid4(), **kwargs)

    def new_position_row(self, **kwargs: Any) -> PaperPositionRow:
        return PaperPositionRow(position_id=uuid4(), **kwargs)
