"""Paper trading orchestrator facade (Phases 4–6)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from market_data.models import StrategyDataBundle
from strategy_engine.models import StrategyParameters

from paper_trading.clock import Clock
from paper_trading.config import PaperTradingConfig
from paper_trading.evaluation import EvaluationResult, PaperEvaluationService
from paper_trading.execution import PaperFillService
from paper_trading.lifecycle import (
    EntryGateContext,
    FillBatchResult,
    FillProcessingContext,
    build_entry_gate_context,
    process_scheduled_intents_for_open,
)
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler import PaperTradingScheduler
from paper_trading.stops import StopLifecycleService


class PaperTradingOrchestrator:
    """Coordinates evaluation, fills, stops, and scheduler jobs."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        config: PaperTradingConfig,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._config = config
        self._evaluation = PaperEvaluationService(repository, clock=clock)
        self._fills = PaperFillService(repository)
        self._stops = StopLifecycleService(repository, config=config)
        self._scheduler = PaperTradingScheduler(
            repository,
            config,
            evaluation_service=self._evaluation,
            fill_service=self._fills,
            stop_service=self._stops,
            clock=clock,
        )

    @property
    def scheduler(self) -> PaperTradingScheduler:
        return self._scheduler

    def evaluate_symbol_for_daily_close(
        self,
        *,
        symbol: str,
        evaluation_time: datetime,
        bundle: StrategyDataBundle,
        strategy_params: StrategyParameters,
        entry_gates: EntryGateContext,
        cycle_id: UUID | None = None,
    ) -> EvaluationResult:
        return self._evaluation.evaluate_symbol_for_daily_close(
            symbol=symbol,
            evaluation_time=evaluation_time,
            bundle=bundle,
            strategy_params=strategy_params,
            config=self._config,
            entry_gates=entry_gates,
            cycle_id=cycle_id,
        )

    def build_entry_gates(
        self,
        *,
        symbol: str,
        entry_ready: bool,
        market_data_ready: bool,
        runtime_paused: bool,
        runtime_kill_switch: bool,
    ) -> EntryGateContext:
        return build_entry_gate_context(
            self._repo,
            symbol=symbol,
            entry_ready=entry_ready,
            market_data_ready=market_data_ready,
            runtime_paused=runtime_paused,
            runtime_kill_switch=runtime_kill_switch,
        )

    def process_scheduled_intents_for_open(
        self,
        *,
        process_time: datetime,
        symbol_contexts: dict[str, FillProcessingContext],
        cycle_id: UUID | None = None,
    ) -> tuple[FillBatchResult, ...]:
        return process_scheduled_intents_for_open(
            self._repo,
            self._fills,
            process_time=process_time,
            fill_delay_seconds=self._config.fill_delay_seconds,
            symbol_contexts=symbol_contexts,
            config=self._config,
            market_data_ready=self._scheduler._market_data_ready,  # noqa: SLF001
            cycle_id=cycle_id,
        )
