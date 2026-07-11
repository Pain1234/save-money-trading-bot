"""Intent creation and scheduled fill lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from backtester.data import evaluation_time_for_daily
from market_data.models import MarketTimeframe
from market_data.timeframes import next_open_time
from risk_engine.models import RiskParameters, SymbolConstraints
from strategy_engine.models import (
    Candle,
    SignalIntentKind,
    StrategyEvaluation,
    StrategyParameters,
)

from paper_trading.config import ALLOWED_SYMBOLS, PaperTradingConfig
from paper_trading.db.orm import TradeIntentRow
from paper_trading.enums import PaperSide, TradeIntentStatus
from paper_trading.execution import EntryExecutionRejected, PaperFillService
from paper_trading.ids import entry_type_to_signal_type, trade_intent_key
from paper_trading.models import (
    PaperExecutionConfig,
    StrategyEvaluationRecord,
    TradeIntent,
)
from paper_trading.repository import PaperTradingRepository
from paper_trading.transitions import TERMINAL_INTENT_STATUSES, validate_intent_transition

SYMBOL_PROCESSING_ORDER: tuple[str, ...] = ("BTC", "ETH", "SOL")

NONTERMINAL_INTENT_STATUSES: tuple[str, ...] = tuple(
    s.value
    for s in TradeIntentStatus
    if s not in TERMINAL_INTENT_STATUSES
)


@dataclass(frozen=True)
class EntryGateContext:
    """Runtime and portfolio gates for new entries."""

    entry_ready: bool
    market_data_ready: bool
    paused: bool
    kill_switch: bool
    open_position_count: int
    has_symbol_position: bool
    has_nonterminal_intent: bool


@dataclass(frozen=True)
class FillProcessingContext:
    """Market and execution inputs for next-open fill processing."""

    open_ref: Decimal
    atr14: Decimal
    candle_open_time: datetime
    constraints: SymbolConstraints
    strategy_params: StrategyParameters
    risk_params: RiskParameters
    execution_config: PaperExecutionConfig
    day_candles: dict[str, Candle]
    prior_closes: dict[str, Decimal]
    processed_intent_ids: frozenset[str]


@dataclass(frozen=True)
class FillBatchResult:
    symbol: str
    processed: int
    filled: int
    rejected: int
    skipped: int


def _next_daily_open_after_signal(daily_candle_open_time: datetime) -> datetime:
    return next_open_time(daily_candle_open_time, MarketTimeframe.DAILY)


def check_entry_gates(
    *,
    symbol: str,
    entry_gates: EntryGateContext,
    strategy_eval: StrategyEvaluation,
    max_open_positions: int = 3,
) -> tuple[str, ...]:
    """Return blocking reasons; empty tuple means entry allowed."""
    blocked: list[str] = []
    if symbol not in ALLOWED_SYMBOLS:
        blocked.append("unsupported_symbol")
    if not entry_gates.entry_ready:
        blocked.append("runtime_not_entry_ready")
    if not entry_gates.market_data_ready:
        blocked.append("market_data_not_ready")
    if entry_gates.paused:
        blocked.append("paused")
    if entry_gates.kill_switch:
        blocked.append("kill_switch")
    if entry_gates.has_symbol_position:
        blocked.append("existing_position")
    if entry_gates.has_nonterminal_intent:
        blocked.append("existing_nonterminal_intent")
    if entry_gates.open_position_count >= max_open_positions:
        blocked.append("max_open_positions")
    if strategy_eval.signal_intent.kind != SignalIntentKind.LONG_ENTRY:
        blocked.append("no_long_entry_signal")
    if strategy_eval.selected_entry_type is None:
        blocked.append("no_selected_entry_type")
    if strategy_eval.signal_intent.stop_initial is None:
        blocked.append("missing_stop")
    if strategy_eval.atr is None or strategy_eval.atr <= 0:
        blocked.append("missing_atr")
    if not strategy_eval.weekly_trend.trend_confirmed:
        blocked.append("weekly_trend_not_confirmed")
    return tuple(blocked)


def create_intent_from_evaluation(
    repo: PaperTradingRepository,
    *,
    evaluation: StrategyEvaluationRecord,
    strategy_eval: StrategyEvaluation,
    entry_gates: EntryGateContext,
    config: PaperTradingConfig,
    cycle_id: UUID | None = None,
    created_at: datetime,
) -> tuple[TradeIntent | None, bool, tuple[str, ...]]:
    blocked = check_entry_gates(
        symbol=evaluation.symbol,
        entry_gates=entry_gates,
        strategy_eval=strategy_eval,
    )
    if blocked:
        return None, False, blocked

    assert strategy_eval.selected_entry_type is not None
    assert strategy_eval.signal_intent.entry_price is not None
    assert strategy_eval.signal_intent.stop_initial is not None

    signal_type = entry_type_to_signal_type(strategy_eval.selected_entry_type)
    scheduled_fill = _next_daily_open_after_signal(evaluation.daily_candle_open_time)
    idem_key = trade_intent_key(
        evaluation.symbol,
        strategy_eval.strategy_version,
        evaluation.evaluation_time,
        signal_type,
    )

    row = TradeIntentRow(
        intent_id=uuid4(),
        idempotency_key=idem_key,
        symbol=evaluation.symbol,
        side=PaperSide.LONG.value,
        signal_type=signal_type.value,
        signal_time=evaluation.evaluation_time,
        scheduled_fill_time=scheduled_fill,
        requested_entry=strategy_eval.signal_intent.entry_price,
        requested_stop=strategy_eval.signal_intent.stop_initial,
        status=TradeIntentStatus.SCHEDULED.value,
        strategy_evaluation_id=evaluation.evaluation_id,
        created_at=created_at,
        updated_at=created_at,
    )
    intent, created = repo.insert_or_get_trade_intent(row)
    return intent, created, ()


def build_entry_gate_context(
    repo: PaperTradingRepository,
    *,
    symbol: str,
    entry_ready: bool,
    market_data_ready: bool,
    runtime_paused: bool,
    runtime_kill_switch: bool,
) -> EntryGateContext:
    open_positions = repo.get_open_positions()
    has_symbol = any(p.symbol == symbol for p in open_positions)
    nonterminal = repo.get_nonterminal_intent_for_symbol(symbol)
    return EntryGateContext(
        entry_ready=entry_ready,
        market_data_ready=market_data_ready,
        paused=runtime_paused,
        kill_switch=runtime_kill_switch,
        open_position_count=len(open_positions),
        has_symbol_position=has_symbol,
        has_nonterminal_intent=nonterminal is not None,
    )


def process_scheduled_intents_for_open(
    repo: PaperTradingRepository,
    fill_service: PaperFillService,
    *,
    process_time: datetime,
    fill_delay_seconds: int,
    symbol_contexts: dict[str, FillProcessingContext],
    cycle_id: UUID | None = None,
) -> tuple[FillBatchResult, ...]:
    """Process due scheduled intents in BTC → ETH → SOL order."""
    if process_time.tzinfo is None:
        raise ValueError("process_time must be timezone-aware UTC")

    results: list[FillBatchResult] = []
    for symbol in SYMBOL_PROCESSING_ORDER:
        ctx = symbol_contexts.get(symbol)
        if ctx is None:
            results.append(
                FillBatchResult(symbol=symbol, processed=0, filled=0, rejected=0, skipped=0)
            )
            continue

        due_time = ctx.candle_open_time + timedelta(seconds=fill_delay_seconds)
        if process_time < due_time:
            results.append(
                FillBatchResult(symbol=symbol, processed=0, filled=0, rejected=0, skipped=0)
            )
            continue

        intents = repo.get_scheduled_intents_for_symbol(symbol, ctx.candle_open_time)
        filled = rejected = skipped = 0
        processed = 0

        for intent in intents:
            if intent.scheduled_fill_time != ctx.candle_open_time:
                skipped += 1
                continue
            processed += 1
            validate_intent_transition(intent.status, TradeIntentStatus.SUBMITTED_TO_PAPER_ENGINE)
            with repo.session.begin():
                repo.update_intent_status(
                    intent.intent_id,
                    TradeIntentStatus.SUBMITTED_TO_PAPER_ENGINE.value,
                    updated_at=process_time,
                )

            outcome = fill_service.execute_scheduled_paper_fill(
                intent=intent,
                atr14=ctx.atr14,
                open_ref=ctx.open_ref,
                candle_open_time=ctx.candle_open_time,
                constraints=ctx.constraints,
                strategy_params=ctx.strategy_params,
                risk_params=ctx.risk_params,
                execution_config=ctx.execution_config,
                day_candles=ctx.day_candles,
                prior_closes=ctx.prior_closes,
                processed_intent_ids=ctx.processed_intent_ids,
                cycle_id=cycle_id,
            )
            if isinstance(outcome, EntryExecutionRejected):
                rejected += 1
            elif outcome.position is not None:
                filled += 1
            else:
                skipped += 1

        results.append(
            FillBatchResult(
                symbol=symbol,
                processed=processed,
                filled=filled,
                rejected=rejected,
                skipped=skipped,
            )
        )
    return tuple(results)


def evaluation_time_from_daily_candle(candle: Candle, delay_seconds: int = 5) -> datetime:
    base = evaluation_time_for_daily(candle)
    if delay_seconds == 5:
        return base
    return candle.close_time + timedelta(seconds=delay_seconds)
