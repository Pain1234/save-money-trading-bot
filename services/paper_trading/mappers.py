"""ORM to domain mappers for paper trading."""

from __future__ import annotations

from paper_trading.db.orm import (
    AuditEventRow,
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
from paper_trading.enums import (
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionStatus,
    PaperSide,
    RuntimeStatus,
    SchedulerRunStatus,
    SignalType,
    TradeIntentStatus,
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


def runtime_row_to_domain(row: RuntimeStateRow) -> RuntimeState:
    return RuntimeState(
        instance_id=row.instance_id,
        status=RuntimeStatus(row.status),
        last_error=row.last_error,
        started_at=row.started_at,
        heartbeat_at=row.heartbeat_at,
        kill_switch=row.kill_switch,
        paused=row.paused,
        current_cycle_id=row.current_cycle_id,
        version=row.version,
    )


def wallet_row_to_domain(row: PaperWalletRow) -> PaperWalletState:
    return PaperWalletState(
        wallet_id=row.wallet_id,
        cash=row.cash,
        total_realized_pnl=row.total_realized_pnl,
        total_fees=row.total_fees,
        total_funding=row.total_funding,
        total_slippage=row.total_slippage,
        version=row.version,
        updated_at=row.updated_at,
    )


def evaluation_row_to_domain(row: StrategyEvaluationRow) -> StrategyEvaluationRecord:
    reasons = row.rejection_reasons
    return StrategyEvaluationRecord(
        evaluation_id=row.evaluation_id,
        symbol=row.symbol,
        evaluation_time=row.evaluation_time,
        daily_candle_open_time=row.daily_candle_open_time,
        weekly_candle_key=row.weekly_candle_key,
        monthly_candle_key=row.monthly_candle_key,
        daily_candle_key=row.daily_candle_key,
        strategy_version=row.strategy_version,
        regime_result=dict(row.regime_result),
        entry_result=dict(row.entry_result),
        rejection_reasons=tuple(str(r) for r in reasons),
        deterministic_input_hash=row.deterministic_input_hash,
        created_at=row.created_at,
    )


def intent_row_to_domain(row: TradeIntentRow) -> TradeIntent:
    return TradeIntent(
        intent_id=row.intent_id,
        idempotency_key=row.idempotency_key,
        symbol=row.symbol,
        side=PaperSide(row.side),
        signal_type=SignalType(row.signal_type),
        signal_time=row.signal_time,
        scheduled_fill_time=row.scheduled_fill_time,
        requested_entry=row.requested_entry,
        requested_stop=row.requested_stop,
        requested_quantity=row.requested_quantity,
        approved_quantity=row.approved_quantity,
        risk_amount=row.risk_amount,
        status=TradeIntentStatus(row.status),
        strategy_evaluation_id=row.strategy_evaluation_id,
        rejection_reason=dict(row.rejection_reason) if row.rejection_reason else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def order_row_to_domain(row: PaperOrderRow) -> PaperOrder:
    return PaperOrder(
        paper_order_id=row.paper_order_id,
        intent_id=row.intent_id,
        symbol=row.symbol,
        side=PaperSide(row.side),
        order_type=PaperOrderType(row.order_type),
        requested_quantity=row.requested_quantity,
        remaining_quantity=row.remaining_quantity,
        expected_fill_time=row.expected_fill_time,
        status=PaperOrderStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def fill_row_to_domain(row: PaperFillRow) -> PaperFill:
    return PaperFill(
        fill_id=row.fill_id,
        paper_order_id=row.paper_order_id,
        symbol=row.symbol,
        side=PaperSide(row.side),
        quantity=row.quantity,
        market_open_price=row.market_open_price,
        slippage=row.slippage,
        fill_price=row.fill_price,
        fee=row.fee,
        fill_time=row.fill_time,
        candle_key=row.candle_key,
        deterministic_fill_key=row.deterministic_fill_key,
        fill_sequence=row.fill_sequence,
    )


def position_row_to_domain(row: PaperPositionRow) -> PaperPosition:
    return PaperPosition(
        position_id=row.position_id,
        symbol=row.symbol,
        status=PaperPositionStatus(row.status),
        quantity=row.quantity,
        average_entry_price=row.average_entry_price,
        initial_stop=row.initial_stop,
        current_stop=row.current_stop,
        highest_close_since_entry=row.highest_close_since_entry,
        entry_atr14=row.entry_atr14,
        realized_pnl=row.realized_pnl,
        unrealized_pnl=row.unrealized_pnl,
        margin_reserved=row.margin_reserved,
        entry_intent_id=row.entry_intent_id,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        version=row.version,
    )


def stop_event_row_to_domain(row: PositionStopHistoryRow) -> PositionStopEvent:
    return PositionStopEvent(
        stop_event_id=row.stop_event_id,
        position_id=row.position_id,
        previous_stop=row.previous_stop,
        new_stop=row.new_stop,
        highest_close=row.highest_close,
        atr=row.atr,
        evaluation_time=row.evaluation_time,
        reason=row.reason,
    )


def snapshot_row_to_domain(row: PortfolioSnapshotRow) -> PortfolioSnapshot:
    return PortfolioSnapshot(
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


def funding_row_to_domain(row: FundingEventRow) -> FundingEventRecord:
    return FundingEventRecord(
        funding_event_id=row.funding_event_id,
        position_id=row.position_id,
        symbol=row.symbol,
        funding_rate=row.funding_rate,
        notional=row.notional,
        amount=row.amount,
        funding_time=row.funding_time,
        deterministic_key=row.deterministic_key,
    )


def scheduler_row_to_domain(row: SchedulerRunRow) -> SchedulerRun:
    return SchedulerRun(
        run_id=row.run_id,
        job_name=row.job_name,
        scheduled_for=row.scheduled_for,
        started_at=row.started_at,
        completed_at=row.completed_at,
        status=SchedulerRunStatus(row.status),
        error=row.error,
        idempotency_key=row.idempotency_key,
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
