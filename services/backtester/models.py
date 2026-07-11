"""Pydantic models for the event-driven backtester."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from risk_engine.constants import RISK_SPECIFICATION_VERSION
from risk_engine.models import RiskParameters, SymbolConstraints
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import (
    EntryType,
    ReasonCode,
    StrategyEvaluation,
    StrategyParameters,
)

from backtester.constants import BACKTESTER_VERSION, DEFAULT_SYMBOLS
from backtester.core_metadata import CORE_ENGINE_METADATA, CoreEngineMetadata


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExitReason(StrEnum):
    STOP_INITIAL = "RC_EXIT_STOP_INITIAL"
    STOP_TRAILING = "RC_EXIT_STOP_TRAILING"
    STOP_GAP = "RC_EXIT_STOP_GAP"
    END_OF_BACKTEST = "END_OF_BACKTEST"


class FeeModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_fee_rate: Decimal = Decimal("0.0005")
    exit_fee_rate: Decimal = Decimal("0.0005")


class SlippageModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    slippage_bps: Decimal = Decimal("5")


class FundingEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    funding_rate: Decimal


class FundingModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False


class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    initial_cash: Decimal = Decimal("100000")
    strategy_params: StrategyParameters = Field(default_factory=StrategyParameters)
    risk_params: RiskParameters = Field(default_factory=RiskParameters)
    fee_model: FeeModel = Field(default_factory=FeeModel)
    slippage_model: SlippageModel = Field(default_factory=SlippageModel)
    funding_model: FundingModel = Field(default_factory=FundingModel)
    symbol_constraints: dict[str, SymbolConstraints] = Field(default_factory=dict)
    initial_processed_intent_ids: tuple[str, ...] = Field(default_factory=tuple)
    backtester_version: str = BACKTESTER_VERSION
    core_metadata: CoreEngineMetadata = Field(default_factory=lambda: CORE_ENGINE_METADATA)


class HistoricalDataBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    daily: dict[str, tuple[Any, ...]]
    weekly: dict[str, tuple[Any, ...]]
    monthly: dict[str, tuple[Any, ...]]
    funding: dict[str, tuple[FundingEvent, ...]] = Field(default_factory=dict)
    data_quality_warnings: tuple[str, ...] = Field(default_factory=tuple)


class BacktestClock(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_time: datetime


class PendingIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_intent_id: str
    symbol: str
    strategy_version: str
    entry_type: EntryType
    strategy_reason_codes: tuple[ReasonCode, ...]
    signal_time: datetime
    order_time: datetime
    signal_close_price: Decimal
    stop_price: Decimal
    atr14: Decimal
    strategy_evaluation: StrategyEvaluation


class SimulatedOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_intent_id: str
    symbol: str
    status: OrderStatus
    quantity: Decimal | None = None
    reference_price: Decimal | None = None


class SimulatedFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal
    fee: Decimal
    slippage_cost: Decimal
    fill_time: datetime


class TrailingStopSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: datetime
    trail_stop: Decimal
    effective_stop: Decimal


class SimulatedPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    initial_stop: Decimal
    trail_stop: Decimal
    effective_stop: Decimal
    highest_close: Decimal
    entry_atr14: Decimal
    client_intent_id: str
    margin_reserved: Decimal


class PortfolioState(BaseModel):
    """Perpetual portfolio snapshot.

    ``cash`` is the wallet balance (fees, funding, realized PnL) — not spot purchase power.
    """

    model_config = ConfigDict(frozen=True)

    cash: Decimal
    positions: tuple[SimulatedPosition, ...] = Field(default_factory=tuple)
    pending_intents: tuple[PendingIntent, ...] = Field(default_factory=tuple)
    total_fees: Decimal = Decimal("0")
    total_funding: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @property
    def wallet_balance_usd(self) -> Decimal:
        return self.cash

    def used_margin_usd(self) -> Decimal:
        return sum((p.margin_reserved for p in self.positions), Decimal("0"))

    def unrealized_pnl_usd(self, mark_prices: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for pos in self.positions:
            mark = mark_prices.get(pos.symbol, pos.entry_price)
            total += pos.quantity * (mark - pos.entry_price)
        return total

    def equity_usd(self, mark_prices: dict[str, Decimal]) -> Decimal:
        return self.cash + self.unrealized_pnl_usd(mark_prices)

    def available_margin_usd(self, mark_prices: dict[str, Decimal]) -> Decimal:
        return max(Decimal("0"), self.equity_usd(mark_prices) - self.used_margin_usd())

    def equity(self, mark_prices: dict[str, Decimal]) -> Decimal:
        """Alias for perpetual equity."""
        return self.equity_usd(mark_prices)


class ExecutionModel(BaseModel):
    """Execution assumptions documented in README."""

    model_config = ConfigDict(frozen=True)

    entry_at_next_open: bool = True
    intrabar_assumption: str = "ENTRY_AT_OPEN_THEN_STOP_SAME_CANDLE"


class BacktestTrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    client_intent_id: str
    strategy_version: str
    entry_type: EntryType
    strategy_reason_codes: tuple[ReasonCode, ...]
    risk_reason_codes: tuple[ReasonCode, ...]
    signal_time: datetime
    order_time: datetime
    entry_time: datetime
    entry_reference_price: Decimal
    entry_fill_price: Decimal
    quantity: Decimal
    initial_stop: Decimal
    trailing_stop_history: tuple[TrailingStopSnapshot, ...] = Field(default_factory=tuple)
    exit_time: datetime | None = None
    exit_reason: ExitReason | None = None
    exit_reference_price: Decimal | None = None
    exit_fill_price: Decimal | None = None
    gross_pnl: Decimal | None = None
    fees: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    net_pnl: Decimal | None = None
    initial_risk_usd: Decimal | None = None
    r_multiple: Decimal | None = None
    holding_period_days: int | None = None


class EquitySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: datetime
    cash: Decimal
    equity: Decimal
    unrealized_pnl: Decimal
    open_positions: int


class DrawdownSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: datetime
    equity: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal


class RiskRejectionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: datetime
    symbol: str
    client_intent_id: str
    reason_codes: tuple[ReasonCode, ...]
    strategy_reason_codes: tuple[ReasonCode, ...]


class SymbolMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    trade_count: int
    net_pnl: Decimal
    win_rate: Decimal | None


class EntryTypeMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_type: EntryType
    trade_count: int
    net_pnl: Decimal
    win_rate: Decimal | None


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_return_pct: Decimal | None
    cagr_pct: Decimal | None
    max_drawdown_pct: Decimal | None
    win_rate: Decimal | None
    profit_factor: Decimal | None
    expectancy_usd: Decimal | None
    expectancy_r: Decimal | None
    average_winner: Decimal | None
    average_loser: Decimal | None
    average_r_multiple: Decimal | None
    max_win_streak: int
    max_loss_streak: int
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    time_in_market_pct: Decimal | None
    trade_count: int
    total_fees: Decimal
    total_funding: Decimal
    total_slippage: Decimal
    per_symbol: tuple[SymbolMetrics, ...] = Field(default_factory=tuple)
    per_entry_type: tuple[EntryTypeMetrics, ...] = Field(default_factory=tuple)


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: BacktestConfig
    core_metadata: CoreEngineMetadata = Field(default_factory=lambda: CORE_ENGINE_METADATA)
    strategy_version: str = STRATEGY_VERSION
    risk_specification_version: str = RISK_SPECIFICATION_VERSION
    data_start: datetime | None
    data_end: datetime | None
    start_capital: Decimal
    end_capital: Decimal
    trades: tuple[BacktestTrade, ...]
    open_positions: tuple[SimulatedPosition, ...]
    equity_curve: tuple[EquitySnapshot, ...]
    drawdown_curve: tuple[DrawdownSnapshot, ...]
    risk_rejections: tuple[RiskRejectionRecord, ...]
    strategy_evaluations: tuple[StrategyEvaluation, ...]
    total_fees: Decimal
    total_funding: Decimal
    total_slippage: Decimal
    data_quality_warnings: tuple[str, ...]
    model_assumptions: tuple[str, ...]
    funding_enabled: bool
    metrics: BacktestMetrics
    processed_intent_ids: tuple[str, ...]
