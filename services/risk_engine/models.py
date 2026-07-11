"""Pydantic data models for Risk Engine V1."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from strategy_engine.models import ReasonCode, SignalIntentKind

from risk_engine.constants import (
    DEFAULT_MAX_LEVERAGE,
    DEFAULT_MAX_OPEN_POSITIONS,
    DEFAULT_MAX_PORTFOLIO_RISK_PCT,
    DEFAULT_RISK_PER_TRADE_PCT,
    DEFAULT_RISK_ROUNDING_TOLERANCE,
    RISK_SPECIFICATION_VERSION,
    STRATEGY_VERSION,
)


class TradeSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class MarketDataStatus(StrEnum):
    OK = "OK"
    INVALID = "INVALID"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"


class BotSystemState(StrEnum):
    OFF = "OFF"
    WARMUP = "WARMUP"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class LossLimitConfig(BaseModel):
    """Optional loss/drawdown limits — disabled by default in V1."""

    model_config = ConfigDict(frozen=True)

    daily_loss_limit_enabled: bool = False
    max_daily_loss_pct: Decimal | None = None
    weekly_loss_limit_enabled: bool = False
    max_weekly_loss_pct: Decimal | None = None
    drawdown_limit_enabled: bool = False
    max_drawdown_pct: Decimal | None = None


class RiskParameters(BaseModel):
    """Specification Freeze 1.0 risk parameters."""

    model_config = ConfigDict(frozen=True)

    risk_specification_version: str = RISK_SPECIFICATION_VERSION
    strategy_version: str = STRATEGY_VERSION
    risk_per_trade_pct: Decimal = DEFAULT_RISK_PER_TRADE_PCT
    max_portfolio_risk_pct: Decimal = DEFAULT_MAX_PORTFOLIO_RISK_PCT
    max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS
    max_leverage: Decimal = DEFAULT_MAX_LEVERAGE
    risk_rounding_tolerance: Decimal = DEFAULT_RISK_ROUNDING_TOLERANCE
    loss_limits: LossLimitConfig = Field(default_factory=LossLimitConfig)


class SymbolConstraints(BaseModel):
    """Exchange constraints for a symbol."""

    model_config = ConfigDict(frozen=True)

    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal = Decimal("0")
    price_tick_size: Decimal


class AccountState(BaseModel):
    """Account snapshot for risk evaluation."""

    model_config = ConfigDict(frozen=True)

    equity_usd: Decimal
    available_margin_usd: Decimal
    daily_realized_pnl_usd: Decimal = Decimal("0")
    weekly_realized_pnl_usd: Decimal = Decimal("0")
    peak_equity_usd: Decimal | None = None


class PositionState(BaseModel):
    """Open position state."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    entry_price: Decimal
    position_size: Decimal
    stop_initial: Decimal
    trail_stop: Decimal
    mark_price: Decimal


class OpenOrderState(BaseModel):
    """Pending entry order that may collide with new intents."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    client_intent_id: str
    side: TradeSide
    is_entry: bool = True


class TradeProposal(BaseModel):
    """Candidate trade from strategy / execution layer."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: TradeSide = TradeSide.LONG
    entry_price: Decimal
    stop_price: Decimal
    client_intent_id: str
    signal_intent_kind: SignalIntentKind
    strategy_approved: bool = False
    market_data_status: MarketDataStatus = MarketDataStatus.OK
    bot_system_state: BotSystemState = BotSystemState.ACTIVE
    atr14: Decimal | None = None


class PositionSizingResult(BaseModel):
    """Intermediate sizing calculation."""

    model_config = ConfigDict(frozen=True)

    risk_budget_usd: Decimal
    stop_distance_usd: Decimal
    raw_quantity: Decimal
    rounded_quantity: Decimal
    actual_trade_risk_usd: Decimal
    actual_trade_risk_pct: Decimal


class PortfolioRiskSnapshot(BaseModel):
    """Portfolio risk before and after proposed trade."""

    model_config = ConfigDict(frozen=True)

    current_open_risk_usd: Decimal
    current_open_risk_pct: Decimal
    projected_portfolio_risk_usd: Decimal
    projected_portfolio_risk_pct: Decimal
    total_notional_usd: Decimal
    projected_notional_usd: Decimal
    effective_leverage: Decimal


class RiskError(BaseModel):
    """Structured risk rejection detail."""

    model_config = ConfigDict(frozen=True)

    code: ReasonCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RiskDecision(BaseModel):
    """Final risk evaluation output."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    symbol: str
    requested_entry_price: Decimal
    requested_stop_price: Decimal
    raw_quantity: Decimal | None = None
    rounded_quantity: Decimal | None = None
    actual_trade_risk_usd: Decimal | None = None
    actual_trade_risk_pct: Decimal | None = None
    current_open_risk_usd: Decimal | None = None
    projected_portfolio_risk_usd: Decimal | None = None
    projected_portfolio_risk_pct: Decimal | None = None
    required_margin_usd: Decimal | None = None
    effective_leverage: Decimal | None = None
    reason_codes: tuple[ReasonCode, ...] = Field(default_factory=tuple)
    strategy_version: str = STRATEGY_VERSION
    risk_specification_version: str = RISK_SPECIFICATION_VERSION
    errors: tuple[RiskError, ...] = Field(default_factory=tuple)
