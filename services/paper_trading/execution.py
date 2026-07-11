"""Pure paper entry/exit calculation and transactional fill execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from backtester.models import PendingIntent, SimulatedPosition
from backtester.paper_lifecycle import (
    EntryAccounting,
    EntryFillComputation,
    ExitAccounting,
    StopTriggerResult,
    compute_entry_accounting,
    compute_entry_fill_prices,
    compute_exit_accounting,
    compute_stop_trigger,
    compute_trailing_stop_update,
    evaluate_entry_risk_decision,
    filter_rejection_reason_codes,
)
from risk_engine.engine import RiskEngine
from risk_engine.models import RiskParameters, SymbolConstraints
from sqlalchemy import select
from strategy_engine.models import Candle, StrategyParameters, TrailingStopState

from paper_trading.accounting import paper_position_to_simulated
from paper_trading.db.orm import PaperFillRow, PaperOrderRow, PaperPositionRow, TradeIntentRow
from paper_trading.db.transaction import transaction_scope
from paper_trading.enums import (
    PaperFillKind,
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionStatus,
    PaperSide,
    TradeIntentStatus,
)
from paper_trading.ids import paper_fill_key
from paper_trading.mappers import (
    fill_row_to_domain,
    intent_row_to_domain,
    order_row_to_domain,
    position_row_to_domain,
)
from paper_trading.models import (
    PaperExecutionConfig,
    PaperFill,
    PaperOrder,
    PaperPosition,
    TradeIntent,
)
from paper_trading.repository import PaperTradingRepository


@dataclass(frozen=True)
class EntryExecutionInput:
    intent: TradeIntent
    open_ref: Decimal
    atr14: Decimal
    candle_open_time: datetime
    constraints: SymbolConstraints
    wallet_cash: Decimal
    open_positions: tuple[PaperPosition, ...]
    pending_intent_ids: frozenset[str]
    processed_intent_ids: frozenset[str]
    day_candles: dict[str, Candle]
    prior_closes: dict[str, Decimal]
    strategy_params: StrategyParameters
    risk_params: RiskParameters
    execution_config: PaperExecutionConfig


@dataclass(frozen=True)
class EntryExecutionRejected:
    approved: bool = False
    reason_codes: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class EntryExecutionApproved:
    approved: bool
    fill_prices: EntryFillComputation
    accounting: EntryAccounting
    quantity: Decimal
    reason_codes: tuple[str, ...]


EntryExecutionResult = EntryExecutionRejected | EntryExecutionApproved


@dataclass(frozen=True)
class TransactionalFillResult:
    created: bool
    fill: PaperFill | None
    order: PaperOrder | None
    position: PaperPosition | None
    intent: TradeIntent


class MissingSymbolConstraintsError(ValueError):
    """Raised when symbol constraints are not provided (fail-closed)."""


def validate_symbol_constraints(constraints: SymbolConstraints | None) -> SymbolConstraints:
    if constraints is None:
        raise MissingSymbolConstraintsError("SymbolConstraints must be explicitly provided")
    if constraints.quantity_step <= 0 or constraints.price_tick_size <= 0:
        raise MissingSymbolConstraintsError("Invalid SymbolConstraints: step and tick must be > 0")
    return constraints


class PaperExecutionEngine:
    """Deterministic paper fill calculations without database side effects."""

    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self._risk = risk_engine or RiskEngine()

    def compute_entry_execution(self, inputs: EntryExecutionInput) -> EntryExecutionResult:
        constraints = validate_symbol_constraints(inputs.constraints)
        if inputs.open_ref <= 0:
            return EntryExecutionRejected(detail="invalid open price")

        fill_prices = compute_entry_fill_prices(
            inputs.open_ref,
            inputs.atr14,
            slippage_bps=inputs.execution_config.slippage_bps,
            strategy_params=inputs.strategy_params,
            price_tick_size=constraints.price_tick_size,
        )

        simulated_open = tuple(paper_position_to_simulated(p) for p in inputs.open_positions)
        pending: tuple[PendingIntent, ...] = ()

        decision = evaluate_entry_risk_decision(
            self._risk,
            symbol=inputs.intent.symbol,
            fill_price=fill_prices.fill_price,
            stop_initial=fill_prices.stop_initial,
            client_intent_id=inputs.intent.idempotency_key,
            atr14=inputs.atr14,
            constraints=constraints,
            wallet_cash=inputs.wallet_cash,
            open_positions=simulated_open,
            pending_intents=pending,
            processed_intent_ids=inputs.processed_intent_ids,
            day_candles=inputs.day_candles,
            prior_closes=inputs.prior_closes,
            risk_params=inputs.risk_params,
        )

        if not decision.approved or decision.rounded_quantity is None:
            codes = tuple(str(c) for c in filter_rejection_reason_codes(decision))
            return EntryExecutionRejected(reason_codes=codes, detail="risk rejected")

        accounting = compute_entry_accounting(
            fill_price=fill_prices.fill_price,
            open_ref=inputs.open_ref,
            quantity=decision.rounded_quantity,
            stop_initial=fill_prices.stop_initial,
            fee_rate=inputs.execution_config.fee_rate,
            slippage_bps=inputs.execution_config.slippage_bps,
            max_leverage=inputs.execution_config.max_leverage,
            strategy_params=inputs.strategy_params,
            price_tick_size=constraints.price_tick_size,
            atr14=inputs.atr14,
        )

        if accounting.fee > inputs.wallet_cash:
            return EntryExecutionRejected(detail="insufficient cash for fee")

        return EntryExecutionApproved(
            approved=True,
            fill_prices=fill_prices,
            accounting=accounting,
            quantity=decision.rounded_quantity,
            reason_codes=tuple(str(c) for c in decision.reason_codes),
        )

    def compute_stop_exit(
        self,
        candle: Candle,
        position: SimulatedPosition,
    ) -> StopTriggerResult | None:
        return compute_stop_trigger(
            candle,
            effective_stop=position.effective_stop,
            initial_stop=position.initial_stop,
            trail_stop=position.trail_stop,
        )

    def compute_exit(
        self,
        exit_reference: Decimal,
        position: SimulatedPosition,
        fee_rate: Decimal,
        slippage_bps: Decimal,
    ) -> ExitAccounting:
        return compute_exit_accounting(
            exit_reference=exit_reference,
            quantity=position.quantity,
            entry_price=position.entry_price,
            slippage_bps=slippage_bps,
            fee_rate=fee_rate,
        )

    def compute_trailing_update(
        self,
        state: TrailingStopState,
        daily_close: Decimal,
        atr14: Decimal,
        strategy_params: StrategyParameters,
        price_tick_size: Decimal,
    ) -> TrailingStopState:
        return compute_trailing_stop_update(
            state, daily_close, atr14, strategy_params, price_tick_size
        )


class PaperFillService:
    """Repository-backed transactional paper fill execution."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        engine: PaperExecutionEngine | None = None,
    ) -> None:
        self._repo = repository
        self._engine = engine or PaperExecutionEngine()

    def execute_scheduled_paper_fill(
        self,
        *,
        intent: TradeIntent,
        atr14: Decimal,
        open_ref: Decimal,
        candle_open_time: datetime,
        constraints: SymbolConstraints,
        strategy_params: StrategyParameters,
        risk_params: RiskParameters,
        execution_config: PaperExecutionConfig,
        day_candles: dict[str, Candle],
        prior_closes: dict[str, Decimal],
        processed_intent_ids: frozenset[str],
        pending_intent_ids: frozenset[str] = frozenset(),
        cycle_id: UUID | None = None,
    ) -> TransactionalFillResult | EntryExecutionRejected:
        validate_symbol_constraints(constraints)
        wallet = self._repo.get_wallet()
        if wallet is None:
            raise LookupError("paper_wallet not seeded")

        existing = self._load_existing_fill(intent, candle_open_time)
        if existing is not None:
            return existing

        open_positions = self._repo.get_open_positions()
        if any(p.symbol == intent.symbol for p in open_positions):
            return EntryExecutionRejected(detail="position already open for symbol")

        calc = self._engine.compute_entry_execution(
            EntryExecutionInput(
                intent=intent,
                open_ref=open_ref,
                atr14=atr14,
                candle_open_time=candle_open_time,
                constraints=constraints,
                wallet_cash=wallet.cash,
                open_positions=open_positions,
                pending_intent_ids=pending_intent_ids,
                processed_intent_ids=processed_intent_ids,
                day_candles=day_candles,
                prior_closes=prior_closes,
                strategy_params=strategy_params,
                risk_params=risk_params,
                execution_config=execution_config,
            )
        )
        if isinstance(calc, EntryExecutionRejected):
            with transaction_scope(self._repo.session):
                self._repo.update_intent_status(
                    intent.intent_id,
                    TradeIntentStatus.REJECTED.value,
                    rejection_reason={
                        "reason_codes": list(calc.reason_codes),
                        "detail": calc.detail,
                    },
                )
                self._repo.append_audit_event(
                    event_type="INTENT_REJECTED",
                    aggregate_type="trade_intent",
                    aggregate_id=intent.intent_id,
                    payload_json={"detail": calc.detail, "reason_codes": list(calc.reason_codes)},
                    cycle_id=cycle_id,
                )
            return calc

        return self._persist_successful_fill(
            intent=intent,
            calc=calc,
            open_ref=open_ref,
            candle_open_time=candle_open_time,
            atr14=atr14,
            cycle_id=cycle_id,
        )

    def _load_existing_fill(
        self,
        intent: TradeIntent,
        candle_open_time: datetime,
    ) -> TransactionalFillResult | None:
        order_row = self._repo.session.execute(
            select(PaperOrderRow).where(PaperOrderRow.intent_id == intent.intent_id)
        ).scalar_one_or_none()
        if order_row is None:
            return None
        fill_key = paper_fill_key(order_row.paper_order_id, candle_open_time, 0)
        fill_row = self._repo.session.execute(
            select(PaperFillRow).where(PaperFillRow.deterministic_fill_key == fill_key)
        ).scalar_one_or_none()
        if fill_row is None:
            return None
        intent_row = self._repo.session.get(TradeIntentRow, intent.intent_id)
        position_row = self._repo.session.execute(
            select(PaperPositionRow).where(PaperPositionRow.entry_intent_id == intent.intent_id)
        ).scalar_one_or_none()
        return TransactionalFillResult(
            created=False,
            fill=fill_row_to_domain(fill_row),
            order=order_row_to_domain(order_row),
            position=position_row_to_domain(position_row) if position_row else None,
            intent=intent_row_to_domain(intent_row) if intent_row else intent,
        )

    def _persist_successful_fill(
        self,
        *,
        intent: TradeIntent,
        calc: EntryExecutionApproved,
        open_ref: Decimal,
        candle_open_time: datetime,
        atr14: Decimal,
        cycle_id: UUID | None,
    ) -> TransactionalFillResult:
        now = candle_open_time
        trail = calc.accounting.trail_state
        with transaction_scope(self._repo.session):
            order_row = PaperOrderRow(
                paper_order_id=uuid4(),
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=PaperSide.LONG.value,
                order_type=PaperOrderType.MARKET_AT_OPEN.value,
                requested_quantity=calc.quantity,
                remaining_quantity=Decimal("0"),
                expected_fill_time=candle_open_time,
                status=PaperOrderStatus.FILLED.value,
                created_at=now,
                updated_at=now,
            )
            order, order_created = self._repo.insert_or_get_paper_order(order_row)
            fill_key = paper_fill_key(order.paper_order_id, candle_open_time, 0)
            fill_row = PaperFillRow(
                fill_id=uuid4(),
                paper_order_id=order.paper_order_id,
                position_id=None,
                fill_kind=PaperFillKind.ENTRY.value,
                symbol=intent.symbol,
                side=PaperSide.LONG.value,
                quantity=calc.quantity,
                market_open_price=open_ref,
                slippage=calc.accounting.slippage_cost,
                fill_price=calc.fill_prices.fill_price,
                fee=calc.accounting.fee,
                fill_time=candle_open_time,
                candle_key=candle_open_time,
                fill_sequence=0,
                deterministic_fill_key=fill_key,
            )
            fill, fill_created = self._repo.insert_or_get_paper_fill(fill_row)
            if not fill_created:
                intent_row = self._repo.session.get(TradeIntentRow, intent.intent_id)
                position_row = self._repo.session.execute(
                    select(PaperPositionRow).where(
                        PaperPositionRow.entry_intent_id == intent.intent_id
                    )
                ).scalar_one_or_none()
                return TransactionalFillResult(
                    created=False,
                    fill=fill,
                    order=order,
                    position=position_row_to_domain(position_row) if position_row else None,
                    intent=intent_row_to_domain(intent_row) if intent_row else intent,
                )

            self._repo.update_wallet(
                cash_delta=-calc.accounting.fee,
                fees_delta=calc.accounting.fee,
                slippage_delta=calc.accounting.slippage_cost,
            )
            position_row = PaperPositionRow(
                position_id=uuid4(),
                symbol=intent.symbol,
                status=PaperPositionStatus.OPEN.value,
                quantity=calc.quantity,
                average_entry_price=calc.fill_prices.fill_price,
                initial_stop=trail.stop_initial,
                current_stop=trail.effective_stop,
                highest_close_since_entry=trail.highest_close,
                entry_atr14=atr14,
                margin_reserved=calc.accounting.margin_reserved,
                entry_intent_id=intent.intent_id,
                opened_at=candle_open_time,
            )
            position = self._repo.create_position(position_row)
            updated_intent = self._repo.update_intent_status(
                intent.intent_id,
                TradeIntentStatus.FILLED.value,
                approved_quantity=calc.quantity,
            )
            self._repo.append_audit_event(
                event_type="PAPER_FILL_EXECUTED",
                aggregate_type="paper_fill",
                aggregate_id=fill.fill_id,
                payload_json={
                    "intent_id": str(intent.intent_id),
                    "symbol": intent.symbol,
                    "quantity": str(calc.quantity),
                    "fill_price": str(calc.fill_prices.fill_price),
                    "atr14": str(atr14),
                },
                cycle_id=cycle_id,
            )
        return TransactionalFillResult(
            created=order_created and fill_created,
            fill=fill,
            order=order,
            position=position,
            intent=updated_intent,
        )
