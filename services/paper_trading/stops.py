"""Trailing stop updates and stop-trigger position closes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from backtester.paper_lifecycle import (
    compute_exit_accounting,
    compute_gap_stop_at_open,
    compute_intraday_stop,
    compute_stop_trigger,
)
from risk_engine.models import SymbolConstraints
from strategy_engine.models import Candle, StrategyParameters, TrailingStopState

from paper_trading.accounting import paper_position_to_simulated
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import PaperFillRow, PaperPositionRow, PositionStopHistoryRow
from paper_trading.db.transaction import transaction_scope
from paper_trading.enums import PaperFillKind, PaperPositionStatus, PaperSide
from paper_trading.execution import PaperExecutionEngine
from paper_trading.ids import paper_exit_fill_key
from paper_trading.lifecycle import SYMBOL_PROCESSING_ORDER
from paper_trading.models import PaperPosition, StrategyEvaluationRecord
from paper_trading.portfolio import PortfolioSnapshotService
from paper_trading.repository import PaperTradingRepository


@dataclass(frozen=True)
class StopUpdateResult:
    position_id: UUID
    updated: bool
    previous_stop: Decimal | None = None
    new_stop: Decimal | None = None


@dataclass(frozen=True)
class StopCloseResult:
    position_id: UUID
    closed: bool
    symbol: str


class StopLifecycleService:
    """
    Stop lifecycle aligned with backtester semantics.

    Trailing stop ATR: uses current daily evaluation ATR when available,
    otherwise falls back to persisted entry_atr14 on the position (backtester parity).
    """

    def __init__(
        self,
        repository: PaperTradingRepository,
        *,
        config: PaperTradingConfig,
        engine: PaperExecutionEngine | None = None,
    ) -> None:
        self._repo = repository
        self._config = config
        self._engine = engine or PaperExecutionEngine()
        self._snapshots = PortfolioSnapshotService(repository)

    def update_daily_trailing_stops(
        self,
        *,
        evaluation_time: datetime,
        daily_candles: dict[str, Candle],
        evaluation_atr_by_symbol: dict[str, Decimal],
        constraints_by_symbol: dict[str, SymbolConstraints],
        strategy_params: StrategyParameters,
        cycle_id: UUID | None = None,
    ) -> tuple[StopUpdateResult, ...]:
        results: list[StopUpdateResult] = []
        for symbol in SYMBOL_PROCESSING_ORDER:
            position = self._repo.get_open_position_for_symbol(symbol)
            if position is None:
                continue
            candle = daily_candles.get(symbol)
            if candle is None or not candle.is_closed:
                results.append(StopUpdateResult(position.position_id, updated=False))
                continue
            constraints = constraints_by_symbol.get(symbol)
            if constraints is None:
                results.append(StopUpdateResult(position.position_id, updated=False))
                continue

            atr = evaluation_atr_by_symbol.get(symbol, position.entry_atr14)
            state = TrailingStopState(
                entry_price=position.average_entry_price,
                stop_initial=position.initial_stop,
                highest_close=position.highest_close_since_entry,
                trail_stop=position.current_stop,
                effective_stop=position.current_stop,
            )
            updated_state = self._engine.compute_trailing_update(
                state,
                candle.close,
                atr,
                strategy_params,
                constraints.price_tick_size,
            )
            if updated_state.effective_stop <= position.current_stop:
                results.append(
                    StopUpdateResult(
                        position.position_id,
                        updated=False,
                        previous_stop=position.current_stop,
                        new_stop=position.current_stop,
                    )
                )
                continue

            with transaction_scope(self._repo.session):
                _, created = self._repo.insert_or_get_stop_event(
                    PositionStopHistoryRow(
                        stop_event_id=uuid4(),
                        position_id=position.position_id,
                        previous_stop=position.current_stop,
                        new_stop=updated_state.effective_stop,
                        highest_close=updated_state.highest_close,
                        atr=atr,
                        evaluation_time=evaluation_time,
                        reason="TRAILING_UPDATE",
                    )
                )
                if not created:
                    results.append(
                        StopUpdateResult(position.position_id, updated=False)
                    )
                    continue
                row = self._repo.session.get(PaperPositionRow, position.position_id)
                assert row is not None
                row.current_stop = updated_state.effective_stop
                row.highest_close_since_entry = updated_state.highest_close
                row.version += 1
                self._repo.session.flush()
                self._repo.append_audit_event(
                    event_type="TRAILING_STOP_UPDATED",
                    aggregate_type="paper_position",
                    aggregate_id=position.position_id,
                    payload_json={
                        "previous_stop": str(position.current_stop),
                        "new_stop": str(updated_state.effective_stop),
                    },
                    cycle_id=cycle_id,
                    created_at=evaluation_time,
                )
            results.append(
                StopUpdateResult(
                    position.position_id,
                    updated=True,
                    previous_stop=position.current_stop,
                    new_stop=updated_state.effective_stop,
                )
            )
            self._snapshots.capture_snapshot(
                evaluation_time=evaluation_time,
                event="trailing_stop_update",
                cycle_id=cycle_id,
            )
        return tuple(results)

    def process_stop_triggers_for_daily_candle(
        self,
        *,
        process_time: datetime,
        daily_candles: dict[str, Candle],
        constraints_by_symbol: dict[str, SymbolConstraints],
        cycle_id: UUID | None = None,
        at_open: bool = False,
    ) -> tuple[StopCloseResult, ...]:
        results: list[StopCloseResult] = []
        for symbol in SYMBOL_PROCESSING_ORDER:
            position = self._repo.get_open_position_for_symbol(symbol)
            if position is None:
                continue
            candle = daily_candles.get(symbol)
            if candle is None:
                continue
            outcome = self._close_if_stopped(
                position=position,
                candle=candle,
                process_time=process_time,
                constraints=constraints_by_symbol.get(symbol),
                cycle_id=cycle_id,
                at_open=at_open,
            )
            results.append(outcome)
        return tuple(results)

    def process_intraday_stop_triggers(
        self,
        *,
        process_time: datetime,
        preview_candles: dict[str, Candle],
        constraints_by_symbol: dict[str, SymbolConstraints],
        cycle_id: UUID | None = None,
    ) -> tuple[StopCloseResult, ...]:
        """Process intraday stop checks using partial live candle lows."""
        results: list[StopCloseResult] = []
        for symbol in SYMBOL_PROCESSING_ORDER:
            position = self._repo.get_open_position_for_symbol(symbol)
            if position is None:
                continue
            candle = preview_candles.get(symbol)
            if candle is None or candle.is_closed:
                continue
            outcome = self._close_if_stopped(
                position=position,
                candle=candle,
                process_time=process_time,
                constraints=constraints_by_symbol.get(symbol),
                cycle_id=cycle_id,
                at_open=False,
                intraday_only=True,
            )
            results.append(outcome)
        return tuple(results)

    def _close_if_stopped(
        self,
        *,
        position: PaperPosition,
        candle: Candle,
        process_time: datetime,
        constraints: SymbolConstraints | None,
        cycle_id: UUID | None,
        at_open: bool = False,
        intraday_only: bool = False,
    ) -> StopCloseResult:
        if constraints is None:
            return StopCloseResult(position.position_id, closed=False, symbol=position.symbol)

        simulated = paper_position_to_simulated(position)
        if at_open:
            trigger = compute_gap_stop_at_open(
                candle,
                effective_stop=simulated.effective_stop,
            )
        elif intraday_only:
            trigger = compute_intraday_stop(
                candle,
                effective_stop=simulated.effective_stop,
                initial_stop=simulated.initial_stop,
                trail_stop=simulated.trail_stop,
            )
        else:
            trigger = compute_stop_trigger(
                candle,
                effective_stop=simulated.effective_stop,
                initial_stop=simulated.initial_stop,
                trail_stop=simulated.trail_stop,
            )
        if trigger is None:
            return StopCloseResult(position.position_id, closed=False, symbol=position.symbol)

        exit_accounting = compute_exit_accounting(
            exit_reference=trigger.exit_reference,
            quantity=position.quantity,
            entry_price=position.average_entry_price,
            slippage_bps=self._config.paper_slippage_bps,
            fee_rate=self._config.paper_fee_rate,
        )

        with transaction_scope(self._repo.session):
            row = self._repo.session.get(PaperPositionRow, position.position_id)
            if row is None or row.status == PaperPositionStatus.CLOSED.value:
                return StopCloseResult(position.position_id, closed=False, symbol=position.symbol)

            exit_fill_key = paper_exit_fill_key(position.position_id, process_time)
            fill_row = PaperFillRow(
                fill_id=uuid4(),
                paper_order_id=None,
                position_id=position.position_id,
                fill_kind=PaperFillKind.EXIT.value,
                symbol=position.symbol,
                side=PaperSide.LONG.value,
                quantity=position.quantity,
                market_open_price=trigger.exit_reference,
                slippage=exit_accounting.slippage_cost,
                fill_price=exit_accounting.fill_price,
                fee=exit_accounting.fee,
                fill_time=process_time,
                candle_key=process_time,
                fill_sequence=0,
                deterministic_fill_key=exit_fill_key,
            )
            _, fill_created = self._repo.insert_or_get_paper_fill(fill_row)
            if not fill_created:
                return StopCloseResult(position.position_id, closed=False, symbol=position.symbol)

            row.status = PaperPositionStatus.CLOSING.value
            self._repo.session.flush()

            self._repo.update_wallet(
                cash_delta=exit_accounting.net_wallet_delta,
                realized_pnl_delta=exit_accounting.gross_pnl - exit_accounting.fee,
                fees_delta=exit_accounting.fee,
                slippage_delta=exit_accounting.slippage_cost,
                updated_at=process_time,
            )

            row.status = PaperPositionStatus.CLOSED.value
            row.closed_at = process_time
            row.realized_pnl = exit_accounting.gross_pnl - exit_accounting.fee
            row.unrealized_pnl = Decimal("0")
            row.margin_reserved = Decimal("0")
            row.version += 1
            self._repo.session.flush()

            self._repo.append_audit_event(
                event_type="POSITION_CLOSED_STOP",
                aggregate_type="paper_position",
                aggregate_id=position.position_id,
                payload_json={
                    "exit_reference": str(trigger.exit_reference),
                    "exit_reason": trigger.exit_reason.value,
                    "fill_price": str(exit_accounting.fill_price),
                },
                cycle_id=cycle_id,
                created_at=process_time,
            )

        self._snapshots.capture_snapshot(
            evaluation_time=process_time,
            event="position_close",
            cycle_id=cycle_id,
        )
        return StopCloseResult(position.position_id, closed=True, symbol=position.symbol)

    @staticmethod
    def atr_for_trailing_update(
        position: PaperPosition,
        latest_evaluation: StrategyEvaluationRecord | None,
        entry_result_atr: Decimal | None = None,
    ) -> Decimal:
        """Match backtester: evaluation ATR at update time, else entry_atr14."""
        if entry_result_atr is not None and entry_result_atr > 0:
            return entry_result_atr
        if latest_evaluation is not None:
            atr_raw = latest_evaluation.entry_result.get("atr")
            if atr_raw is not None:
                return Decimal(str(atr_raw))
        return position.entry_atr14
