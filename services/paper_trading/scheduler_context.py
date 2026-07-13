"""Production scheduler context assembly from market data."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle, StrategyDataBundle
from market_data.service import MarketDataService
from risk_engine.models import RiskParameters, SymbolConstraints
from strategy_engine.constants import (
    MIN_DAILY_CANDLES,
    MIN_MONTHLY_CANDLES,
    MIN_WEEKLY_CANDLES,
)
from strategy_engine.models import Candle, StrategyParameters

from paper_trading.clock import Clock
from paper_trading.config import PaperTradingConfig
from paper_trading.constraint_validation import require_valid_production_constraints
from paper_trading.enums import RuntimeStatus
from paper_trading.lifecycle import (
    FillProcessingContext,
    build_entry_gate_context,
)
from paper_trading.market_event_errors import (
    RetryableContextNotReady,
)
from paper_trading.models import PaperExecutionConfig
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler_context_diagnostics import (
    build_daily_open_defer_snapshot,
    format_daily_open_defer_log,
)
from paper_trading.stops import StopLifecycleService
from paper_trading.symbol_constraints import SymbolConstraintsProvider


class ProductionContextBuilder:
    """Build scheduler job inputs from persisted market data."""

    def __init__(
        self,
        *,
        market_data: MarketDataService,
        repository: PaperTradingRepository,
        config: PaperTradingConfig,
        constraints: SymbolConstraintsProvider,
        clock: Clock,
        strategy_params: StrategyParameters | None = None,
        risk_params: RiskParameters | None = None,
        execution_config: PaperExecutionConfig | None = None,
        market_data_ready: Callable[[], bool] | None = None,
    ) -> None:
        if market_data_ready is None:
            raise ValueError("market_data_ready source is required")
        self._market_data = market_data
        self._repo = repository
        self._config = config
        self._constraints = constraints
        self._clock = clock
        self._strategy_params = strategy_params or StrategyParameters()
        self._risk_params = risk_params or RiskParameters(
            risk_per_trade_pct=Decimal("0.005"),
            max_portfolio_risk_pct=Decimal("0.02"),
            max_leverage=config.paper_max_leverage,
        )
        self._execution_config = execution_config or PaperExecutionConfig.from_trading_config(
            config
        )
        self._market_data_ready = market_data_ready

    def _bundle(
        self,
        symbol: str,
        evaluation_time: datetime,
        *,
        backfill: bool = False,
    ) -> StrategyDataBundle:
        return self._market_data.build_strategy_bundle(
            MarketSymbol(symbol),
            evaluation_time,
            MIN_DAILY_CANDLES,
            MIN_WEEKLY_CANDLES,
            MIN_MONTHLY_CANDLES,
            backfill=backfill,
            aggregate_higher_timeframes=False,
        )

    def _runtime_gates(self) -> tuple[bool, bool, bool]:
        runtime = self._repo.get_runtime_state()
        if runtime is None:
            return False, False, False
        paused = runtime.status == RuntimeStatus.PAUSED
        kill = runtime.kill_switch
        entry_ready = runtime.status == RuntimeStatus.READY and not kill and not paused
        return entry_ready, paused, kill

    def validate_symbol_configuration(self, symbol: str) -> None:
        """Fail-closed constraint validation for recovery and readiness."""
        constraints = self._constraints.get(symbol)
        require_valid_production_constraints(symbol=symbol, constraints=constraints)

    def _require_valid_constraints(self, symbol: str) -> SymbolConstraints:
        constraints = self._constraints.get(symbol)
        return require_valid_production_constraints(symbol=symbol, constraints=constraints)

    def build_evaluation_context(
        self,
        symbol: str,
        evaluation_time: datetime,
    ) -> dict[str, object]:
        self._require_valid_constraints(symbol)
        bundle = self._bundle(symbol, evaluation_time, backfill=False)
        if not bundle.is_usable:
            raise RetryableContextNotReady(
                f"strategy bundle not usable for {symbol} at {evaluation_time.isoformat()}"
            )
        entry_ready, paused, kill = self._runtime_gates()
        entry_gates = build_entry_gate_context(
            self._repo,
            symbol=symbol,
            entry_ready=entry_ready,
            market_data_ready=self._market_data_ready(),
            runtime_paused=paused,
            runtime_kill_switch=kill,
        )
        return {
            "symbols": {
                symbol: {
                    "bundle": bundle,
                    "strategy_params": self._strategy_params,
                    "config": self._config,
                    "entry_gates": entry_gates,
                }
            }
        }

    def build_stop_context_for_close(
        self,
        symbol: str,
        evaluation_time: datetime,
    ) -> dict[str, object]:
        constraints = self._require_valid_constraints(symbol)
        bundle = self._bundle(symbol, evaluation_time, backfill=False)
        if not bundle.daily.candles:
            raise RetryableContextNotReady(
                f"daily history missing for {symbol} at {evaluation_time.isoformat()}"
            )
        last_daily = bundle.daily.candles[-1]
        if not last_daily.is_closed:
            raise RetryableContextNotReady(
                f"latest daily candle not closed for {symbol}"
            )
        atr_by_symbol: dict[str, Decimal] = {}
        position = self._repo.get_open_position_for_symbol(symbol)
        if position is not None:
            evaluations = self._repo.list_evaluations(limit=100)
            latest_eval = next((item for item in evaluations if item.symbol == symbol), None)
            atr_by_symbol[symbol] = StopLifecycleService.atr_for_trailing_update(
                position,
                latest_eval,
            )
        return {
            "daily_candles": {symbol: last_daily},
            "evaluation_atr_by_symbol": atr_by_symbol,
            "constraints_by_symbol": {symbol: constraints},
            "strategy_params": self._strategy_params,
        }

    def build_open_contexts(
        self,
        symbol: str,
        open_candle: NormalizedCandle,
        evaluation_time: datetime,
    ) -> tuple[dict[str, FillProcessingContext], dict[str, object]]:
        constraints = self._require_valid_constraints(symbol)

        prior_eval_time = open_candle.open_time
        bundle = self._bundle(symbol, prior_eval_time, backfill=False)
        if not bundle.is_usable or not bundle.daily.candles:
            raise RetryableContextNotReady(
                f"strategy bundle not usable for {symbol} at {prior_eval_time.isoformat()}"
            )

        from strategy_engine.engine import StrategyEngine

        engine = StrategyEngine()
        strategy_eval = engine.evaluate(
            bundle.daily,
            bundle.weekly,
            bundle.monthly,
            prior_eval_time,
            self._strategy_params,
        )
        atr14 = strategy_eval.atr
        if atr14 is None or atr14 <= 0:
            raise RetryableContextNotReady(
                f"atr14 not available for {symbol} at {prior_eval_time.isoformat()}"
            )

        prior_closes: dict[str, Decimal] = {}
        repo = self._market_data.repository
        for sym in self._config.symbols:
            closed = repo.get_closed_before(
                MarketSymbol(sym), MarketTimeframe.DAILY, open_candle.open_time
            )
            if closed:
                prior_closes[sym] = closed[-1].close

        day_candle = _open_only_strategy_candle(open_candle)
        fill_ctx = FillProcessingContext(
            open_ref=open_candle.open,
            atr14=atr14,
            candle_open_time=open_candle.open_time,
            constraints=constraints,
            strategy_params=self._strategy_params,
            risk_params=self._risk_params,
            execution_config=self._execution_config,
            day_candles={symbol: day_candle},
            prior_closes=prior_closes,
            processed_intent_ids=frozenset(),
        )

        gap_candle = _gap_check_strategy_candle(open_candle)
        stop_ctx = {
            "daily_candles": {symbol: gap_candle},
            "constraints_by_symbol": {symbol: constraints},
        }
        return {symbol: fill_ctx}, stop_ctx

    def describe_daily_open_defer(
        self,
        symbol: str,
        *,
        open_candle: NormalizedCandle | None,
        prior_eval_time: datetime | None,
        evaluation_time: datetime,
        error: RetryableContextNotReady,
        event_name: str = "daily_open_deferred",
    ) -> str:
        """Build a Railway-visible log line for daily open defer diagnostics."""
        resolved_prior = prior_eval_time
        if resolved_prior is None and open_candle is not None:
            resolved_prior = open_candle.open_time
        snapshot = build_daily_open_defer_snapshot(
            symbol=symbol,
            error=error,
            market_data_service=self._market_data,
            strategy_params=self._strategy_params,
            market_data_ready=self._market_data_ready(),
            prior_eval_time=resolved_prior,
            evaluation_time=evaluation_time,
            build_strategy_bundle=self._market_data.build_strategy_bundle,
        )
        return format_daily_open_defer_log(snapshot, event_name=event_name)

    def build_intraday_stop_context(
        self,
        symbol: str,
        live_candle: NormalizedCandle,
    ) -> dict[str, object]:
        constraints = self._require_valid_constraints(symbol)
        if live_candle.is_closed:
            raise RetryableContextNotReady(f"live candle closed for {symbol}")
        preview = live_candle.to_strategy_candle()
        return {
            "preview_candles": {symbol: preview},
            "constraints_by_symbol": {symbol: constraints},
        }


def _open_only_strategy_candle(candle: NormalizedCandle) -> Candle:
    """Open-known candle without look-ahead from future lows."""
    return Candle(
        symbol=candle.symbol.value,
        timeframe=candle.timeframe.to_strategy_timeframe(),
        open_time=candle.open_time,
        close_time=candle.close_time,
        open=candle.open,
        high=candle.open,
        low=candle.open,
        close=candle.open,
        volume=candle.volume,
        is_closed=False,
    )


def _gap_check_strategy_candle(candle: NormalizedCandle) -> Candle:
    """Gap stop uses open only — no intraday low."""
    return Candle(
        symbol=candle.symbol.value,
        timeframe=candle.timeframe.to_strategy_timeframe(),
        open_time=candle.open_time,
        close_time=candle.close_time,
        open=candle.open,
        high=candle.high,
        low=candle.open,
        close=candle.close,
        volume=candle.volume,
        is_closed=candle.is_closed,
    )
