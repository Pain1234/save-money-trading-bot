"""Strategy evaluation application service for paper trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from backtester.data import evaluation_time_for_daily
from market_data.models import StrategyDataBundle
from strategy_engine.engine import StrategyEngine
from strategy_engine.models import SignalIntentKind, StrategyParameters

from paper_trading.clock import Clock
from paper_trading.config import ALLOWED_SYMBOLS, PaperTradingConfig
from paper_trading.db.orm import StrategyEvaluationRow
from paper_trading.db.transaction import transaction_scope
from paper_trading.ids import deterministic_input_hash
from paper_trading.lifecycle import EntryGateContext, create_intent_from_evaluation
from paper_trading.models import StrategyEvaluationRecord, TradeIntent
from paper_trading.repository import PaperTradingRepository
from paper_trading.serialization import (
    evaluation_hash_payload,
    evaluation_rejection_reasons,
    evaluation_to_entry_result,
    evaluation_to_regime_result,
)


@dataclass(frozen=True)
class EvaluationResult:
    evaluation: StrategyEvaluationRecord
    created: bool
    intent: TradeIntent | None
    intent_created: bool
    blocked_reasons: tuple[str, ...] = ()


class PaperEvaluationService:
    """Evaluate strategy at daily close and persist results idempotently."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        strategy_engine: StrategyEngine | None = None,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._strategy = strategy_engine or StrategyEngine()
        self._clock = clock

    def evaluate_symbol_for_daily_close(
        self,
        *,
        symbol: str,
        evaluation_time: datetime,
        bundle: StrategyDataBundle,
        strategy_params: StrategyParameters,
        config: PaperTradingConfig,
        entry_gates: EntryGateContext,
        cycle_id: UUID | None = None,
    ) -> EvaluationResult:
        if symbol not in ALLOWED_SYMBOLS:
            raise ValueError(f"unsupported symbol: {symbol}")
        if evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware UTC")

        if not bundle.is_usable:
            reasons = tuple(str(c) for c in bundle.report.reason_codes)
            raise ValueError(f"market data not ready: {reasons}")

        daily = bundle.daily
        if not daily.candles:
            raise ValueError("no closed daily candles available")

        last_daily = daily.candles[-1]
        expected_eval = evaluation_time_for_daily(last_daily)
        if evaluation_time < expected_eval:
            raise ValueError("evaluation_time before daily close event")

        strategy_eval = self._strategy.evaluate(
            daily,
            bundle.weekly,
            bundle.monthly,
            evaluation_time,
            strategy_params,
        )

        daily_open = last_daily.open_time
        created_at = evaluation_time
        payload = evaluation_hash_payload(
            strategy_eval,
            daily_candle_open_time=daily_open.isoformat(),
        )
        input_hash = deterministic_input_hash(payload)

        weekly_key = (
            bundle.weekly.candles[-1].open_time if bundle.weekly.candles else daily_open
        )
        monthly_key = (
            bundle.monthly.candles[-1].open_time if bundle.monthly.candles else daily_open
        )
        row = StrategyEvaluationRow(
            evaluation_id=uuid4(),
            symbol=symbol,
            evaluation_time=evaluation_time,
            daily_candle_open_time=daily_open,
            weekly_candle_key=weekly_key,
            monthly_candle_key=monthly_key,
            daily_candle_key=daily_open,
            strategy_version=strategy_eval.strategy_version,
            regime_result=evaluation_to_regime_result(strategy_eval),
            entry_result=evaluation_to_entry_result(strategy_eval),
            rejection_reasons=list(evaluation_rejection_reasons(strategy_eval)),
            deterministic_input_hash=input_hash,
            created_at=created_at,
        )

        with transaction_scope(self._repo.session):
            evaluation, created = self._repo.insert_or_get_strategy_evaluation(row)
            self._repo.append_audit_event(
                event_type="STRATEGY_EVALUATION_RECORDED",
                aggregate_type="strategy_evaluation",
                aggregate_id=evaluation.evaluation_id,
                payload_json={
                    "symbol": symbol,
                    "created": created,
                    "signal_kind": strategy_eval.signal_intent.kind.value,
                },
                cycle_id=cycle_id,
                created_at=created_at,
            )

            intent: TradeIntent | None = None
            intent_created = False
            blocked: tuple[str, ...] = ()

            if strategy_eval.signal_intent.kind == SignalIntentKind.LONG_ENTRY:
                intent, intent_created, blocked = create_intent_from_evaluation(
                    self._repo,
                    evaluation=evaluation,
                    strategy_eval=strategy_eval,
                    entry_gates=entry_gates,
                    config=config,
                    cycle_id=cycle_id,
                    created_at=created_at,
                    authorization_at=(
                        self._clock.now() if self._clock is not None else evaluation_time
                    ),
                )
                if intent is not None and intent_created:
                    self._repo.append_audit_event(
                        event_type="TRADE_INTENT_CREATED",
                        aggregate_type="trade_intent",
                        aggregate_id=intent.intent_id,
                        payload_json={
                            "symbol": symbol,
                            "signal_type": intent.signal_type.value,
                            "scheduled_fill_time": intent.scheduled_fill_time.isoformat(),
                        },
                        cycle_id=cycle_id,
                        created_at=created_at,
                    )

        return EvaluationResult(
            evaluation=evaluation,
            created=created,
            intent=intent,
            intent_created=intent_created,
            blocked_reasons=blocked,
        )

    @staticmethod
    def is_evaluation_due(
        *,
        daily_close_time: datetime,
        process_time: datetime,
        evaluation_delay_seconds: int,
    ) -> bool:
        due_at = daily_close_time + timedelta(seconds=evaluation_delay_seconds)
        return process_time >= due_at
