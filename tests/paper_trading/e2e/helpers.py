# ruff: noqa: E402
"""Shared helpers for paper trading E2E, replay, failure, and soak tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

_SERVICES = Path(__file__).resolve().parents[3] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from backtester.data import evaluation_time_for_daily
from backtester.models import HistoricalDataBundle
from market_data.models import (
    DataQualityReport,
    DataQualityStatus,
    MarketSymbol,
    StrategyDataBundle,
)
from paper_trading.clock import Clock, FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import (
    RuntimeStatus,
)
from paper_trading.lifecycle import FillProcessingContext
from paper_trading.orchestrator import PaperTradingOrchestrator
from paper_trading.repository import PaperTradingRepository
from risk_engine.models import RiskParameters
from strategy_engine.models import Candle, CandleSeries, StrategyParameters, Timeframe

from tests.backtester.conftest import DEFAULT_CONSTRAINTS, dt, make_config
from tests.paper_trading.conftest_execution import EXECUTION_CONFIG
from tests.strategy_engine.conftest import (
    build_flat_daily_series,
    build_rising_monthly_series,
    build_rising_weekly_series,
    make_daily_candle,
)

SYMBOLS: tuple[str, ...] = ("BTC", "ETH", "SOL")
DEFAULT_RISK = RiskParameters(
    risk_per_trade_pct=Decimal("0.005"),
    max_portfolio_risk_pct=Decimal("0.02"),
    max_leverage=Decimal("2"),
)


def build_breakout_historical_bundle(
    symbol: str = "BTC",
    *,
    include_exit_candle: bool = True,
) -> HistoricalDataBundle:
    """Deterministic breakout bundle aligned with backtester E2E reference."""
    daily_cs = build_flat_daily_series(symbol, 30, start=dt(2024, 1, 1))
    candles = list(daily_cs.candles)
    last = candles[-1]
    candles[-1] = make_daily_candle(
        symbol,
        last.open_time,
        "100",
        "130",
        "99",
        "125",
        vol="2000",
    )
    if include_exit_candle:
        fill_open = last.open_time + timedelta(days=1)
        candles.append(
            make_daily_candle(symbol, fill_open, "100", "101", "86", "89", vol="1000")
        )
    weekly = build_rising_weekly_series(symbol, 55, start_price=Decimal("100"))
    monthly = build_rising_monthly_series(symbol, 25, start_price=Decimal("100"))
    return HistoricalDataBundle(
        daily={symbol: tuple(candles)},
        weekly={symbol: weekly.candles},
        monthly={symbol: monthly.candles},
    )


def build_extended_lifecycle_bundle(symbol: str = "BTC") -> HistoricalDataBundle:
    """Breakout, fill, rising closes, then stop exit."""
    daily_cs = build_flat_daily_series(symbol, 30, start=dt(2024, 1, 1))
    candles = list(daily_cs.candles)
    last = candles[-1]
    candles[-1] = make_daily_candle(
        symbol, last.open_time, "100", "130", "99", "125", vol="2000"
    )
    fill_open = last.open_time + timedelta(days=1)
    candles.append(make_daily_candle(symbol, fill_open, "100", "105", "95", "102", vol="1000"))
    for i, close in enumerate(["104", "108", "112", "115"], start=2):
        open_time = fill_open + timedelta(days=i - 1)
        candles.append(
            make_daily_candle(symbol, open_time, close, str(int(close) + 2), "98", close, vol="900")
        )
    exit_open = fill_open + timedelta(days=5)
    candles.append(make_daily_candle(symbol, exit_open, "112", "113", "85", "88", vol="1100"))
    weekly = build_rising_weekly_series(symbol, 55, start_price=Decimal("100"))
    monthly = build_rising_monthly_series(symbol, 25, start_price=Decimal("100"))
    return HistoricalDataBundle(
        daily={symbol: tuple(candles)},
        weekly={symbol: weekly.candles},
        monthly={symbol: monthly.candles},
    )


def historical_to_strategy_bundle(
    bundle: HistoricalDataBundle,
    symbol: str,
    *,
    daily_count: int | None = None,
) -> tuple[StrategyDataBundle, datetime]:
    dailies = bundle.daily[symbol]
    if daily_count is not None:
        dailies = dailies[:daily_count]
    eval_candle = dailies[-1]
    evaluation_time = evaluation_time_for_daily(eval_candle)
    daily = CandleSeries(symbol=symbol, timeframe=Timeframe.DAILY, candles=dailies)
    weekly = CandleSeries(
        symbol=symbol,
        timeframe=Timeframe.WEEKLY,
        candles=bundle.weekly[symbol],
    )
    monthly = CandleSeries(
        symbol=symbol,
        timeframe=Timeframe.MONTHLY,
        candles=bundle.monthly[symbol],
    )
    report = DataQualityReport(
        status=DataQualityStatus.VALID,
        reason_codes=(),
        evaluation_time=evaluation_time,
    )
    return (
        StrategyDataBundle(
            symbol=MarketSymbol(symbol),
            evaluation_time=evaluation_time,
            daily=daily,
            weekly=weekly,
            monthly=monthly,
            report=report,
        ),
        evaluation_time,
    )


def candle_at(bundle: HistoricalDataBundle, symbol: str, index: int) -> Candle:
    return bundle.daily[symbol][index]


def evaluation_atr(
    bundle: StrategyDataBundle,
    evaluation_time: datetime,
    strategy_params: StrategyParameters | None = None,
) -> Decimal:
    from strategy_engine.engine import StrategyEngine

    params = strategy_params or StrategyParameters()
    evaluation = StrategyEngine().evaluate(
        bundle.daily,
        bundle.weekly,
        bundle.monthly,
        evaluation_time,
        params,
    )
    assert evaluation.atr is not None and evaluation.atr > 0
    return evaluation.atr


def fill_context_for_bundle(
    bundle: StrategyDataBundle,
    evaluation_time: datetime,
    fill_candle: Candle,
    *,
    strategy_params: StrategyParameters | None = None,
    prior_close: Decimal | None = None,
) -> FillProcessingContext:
    atr = evaluation_atr(bundle, evaluation_time, strategy_params)
    return fill_context_for_candle(
        fill_candle,
        atr14=atr,
        prior_close=prior_close,
    )


def fill_context_for_candle(
    candle: Candle,
    *,
    atr14: Decimal = Decimal("1000"),
    prior_close: Decimal | None = None,
) -> FillProcessingContext:
    prior = prior_close if prior_close is not None else candle.open
    return FillProcessingContext(
        open_ref=candle.open,
        atr14=atr14,
        candle_open_time=candle.open_time,
        constraints=DEFAULT_CONSTRAINTS,
        strategy_params=StrategyParameters(),
        risk_params=DEFAULT_RISK,
        execution_config=EXECUTION_CONFIG,
        day_candles={candle.symbol: candle},
        prior_closes={candle.symbol: prior},
        processed_intent_ids=frozenset(),
    )


@dataclass
class HarnessCounts:
    evaluations: int
    intents: int
    orders: int
    fills: int
    open_positions: int
    audit_events: int


class PaperE2EHarness:
    """Drive the paper trading orchestrator through deterministic daily steps."""

    def __init__(
        self,
        repository: PaperTradingRepository,
        config: PaperTradingConfig,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.repo = repository
        self.config = config
        self.clock = clock or FixedClock(datetime(2024, 1, 1, tzinfo=UTC))
        self.orchestrator = PaperTradingOrchestrator(repository, config, clock=self.clock)
        self.strategy_params = StrategyParameters()
        self.risk_params = DEFAULT_RISK

    def set_runtime_ready(self) -> None:
        runtime = self.repo.get_runtime_state()
        assert runtime is not None
        self.repo.update_runtime_state(
            status=RuntimeStatus.READY,
            expected_version=runtime.version,
        )

    def entry_gates(self, symbol: str) -> Any:
        runtime = self.repo.get_runtime_state()
        assert runtime is not None
        return self.orchestrator.build_entry_gates(
            symbol=symbol,
            entry_ready=True,
            market_data_ready=True,
            runtime_paused=runtime.paused,
            runtime_kill_switch=runtime.kill_switch,
        )

    def evaluate_at_close(
        self,
        symbol: str,
        bundle: StrategyDataBundle,
        evaluation_time: datetime,
    ) -> Any:
        return self.orchestrator.evaluate_symbol_for_daily_close(
            symbol=symbol,
            evaluation_time=evaluation_time,
            bundle=bundle,
            strategy_params=self.strategy_params,
            entry_gates=self.entry_gates(symbol),
        )

    def fill_at_open(
        self,
        *,
        process_time: datetime,
        symbol_contexts: dict[str, FillProcessingContext],
    ) -> tuple[Any, ...]:
        return self.orchestrator.process_scheduled_intents_for_open(
            process_time=process_time,
            symbol_contexts=symbol_contexts,
        )

    def process_stops(
        self,
        *,
        process_time: datetime,
        daily_candles: dict[str, Candle],
    ) -> tuple[Any, ...]:
        return self.orchestrator._stops.process_stop_triggers_for_daily_candle(
            process_time=process_time,
            daily_candles=daily_candles,
            constraints_by_symbol={s: DEFAULT_CONSTRAINTS for s in SYMBOLS},
        )

    def update_trailing(
        self,
        *,
        evaluation_time: datetime,
        daily_candles: dict[str, Candle],
        atr_by_symbol: dict[str, Decimal],
    ) -> tuple[Any, ...]:
        return self.orchestrator._stops.update_daily_trailing_stops(
            evaluation_time=evaluation_time,
            daily_candles=daily_candles,
            evaluation_atr_by_symbol=atr_by_symbol,
            constraints_by_symbol={s: DEFAULT_CONSTRAINTS for s in SYMBOLS},
            strategy_params=self.strategy_params,
        )

    def counts(self) -> HarnessCounts:
        return HarnessCounts(
            evaluations=len(self.repo.list_evaluations(limit=10_000)),
            intents=len(self.repo.list_intents(limit=10_000)),
            orders=len(self.repo.list_orders(limit=10_000)),
            fills=len(self.repo.list_fills(limit=10_000)),
            open_positions=len(self.repo.get_open_positions()),
            audit_events=len(self.repo.list_audit_events(limit=10_000)),
        )

    def wallet_cash(self) -> Decimal:
        wallet = self.repo.get_wallet()
        assert wallet is not None
        return wallet.cash


def backtest_config_for_symbols(symbols: tuple[str, ...]) -> Any:
    return make_config(
        symbols,
        initial_cash="100000",
        fee_entry="0.0005",
        fee_exit="0.0005",
        slippage_bps="5",
        funding_enabled=False,
        risk_params=DEFAULT_RISK,
    )


def paper_config_from_env(database_url: str) -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url=database_url,
        paper_fee_rate=Decimal("0.0005"),
        paper_slippage_bps=Decimal("5"),
        paper_max_leverage=Decimal("2"),
        fill_delay_seconds=0,
        evaluation_delay_seconds=5,
    )
