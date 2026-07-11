"""Pydantic data models for Strategy Engine V1."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from strategy_engine.constants import (
    DEFAULT_ATR_PERIOD,
    DEFAULT_BREAKOUT_LOOKBACK,
    DEFAULT_DAILY_EMA_PERIOD,
    DEFAULT_MONTHLY_EMA_PERIOD,
    DEFAULT_PULLBACK_EMA_TOLERANCE,
    DEFAULT_STOP_INITIAL_ATR_MULT,
    DEFAULT_TRAIL_ATR_MULT,
    DEFAULT_VOLUME_RATIO_MIN,
    DEFAULT_VOLUME_SMA_PERIOD,
    DEFAULT_WEEKLY_EMA_FAST,
    DEFAULT_WEEKLY_EMA_SLOW,
    STRATEGY_VERSION,
)


class Timeframe(StrEnum):
    """Supported candle timeframes."""

    DAILY = "1D"
    WEEKLY = "1W"
    MONTHLY = "1M"


class ReasonCode(StrEnum):
    """Machine-readable reason codes (Strategy Spec §10)."""

    RC_ENTRY_BREAKOUT_20D = "RC_ENTRY_BREAKOUT_20D"
    RC_ENTRY_PULLBACK_EMA20 = "RC_ENTRY_PULLBACK_EMA20"
    RC_EXIT_STOP_INITIAL = "RC_EXIT_STOP_INITIAL"
    RC_EXIT_STOP_TRAILING = "RC_EXIT_STOP_TRAILING"
    RC_EXIT_STOP_GAP = "RC_EXIT_STOP_GAP"
    RC_EXIT_REGIME_MONTHLY = "RC_EXIT_REGIME_MONTHLY"
    RC_EXIT_MANUAL = "RC_EXIT_MANUAL"
    RC_REJECT_REGIME = "RC_REJECT_REGIME"
    RC_REJECT_TREND = "RC_REJECT_TREND"
    RC_REJECT_VOLUME = "RC_REJECT_VOLUME"
    RC_REJECT_WARMUP = "RC_REJECT_WARMUP"
    RC_REJECT_DATA = "RC_REJECT_DATA"
    RC_REJECT_DUPLICATE_SYMBOL = "RC_REJECT_DUPLICATE_SYMBOL"
    RC_REJECT_RISK_TRADE = "RC_REJECT_RISK_TRADE"
    RC_REJECT_RISK_PORTFOLIO = "RC_REJECT_RISK_PORTFOLIO"
    RC_REJECT_MAX_POSITIONS = "RC_REJECT_MAX_POSITIONS"
    RC_REJECT_LEVERAGE = "RC_REJECT_LEVERAGE"
    RC_REJECT_NO_SIGNAL = "RC_REJECT_NO_SIGNAL"
    RC_RISK_APPROVED = "RC_RISK_APPROVED"


class EntryType(StrEnum):
    """Daily entry model type."""

    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"


class SignalIntentKind(StrEnum):
    """High-level signal intent for strategy evaluation output."""

    LONG_ENTRY = "LONG_ENTRY"
    NO_ENTRY = "NO_ENTRY"
    INVALID_DATA = "INVALID_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class DataQualityStatus(StrEnum):
    """Data quality assessment result."""

    OK = "OK"
    INVALID_DATA = "INVALID_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class Candle(BaseModel):
    """Single OHLCV candle with UTC timestamps."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool


class CandleSeries(BaseModel):
    """Ordered collection of candles for one symbol and timeframe."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    candles: tuple[Candle, ...] = Field(default_factory=tuple)

    @property
    def length(self) -> int:
        return len(self.candles)


class StrategyParameters(BaseModel):
    """Specification Freeze 1.0 strategy parameters."""

    model_config = ConfigDict(frozen=True)

    strategy_version: str = STRATEGY_VERSION
    monthly_ema_period: int = DEFAULT_MONTHLY_EMA_PERIOD
    weekly_ema_fast: int = DEFAULT_WEEKLY_EMA_FAST
    weekly_ema_slow: int = DEFAULT_WEEKLY_EMA_SLOW
    daily_ema_period: int = DEFAULT_DAILY_EMA_PERIOD
    breakout_lookback: int = DEFAULT_BREAKOUT_LOOKBACK
    atr_period: int = DEFAULT_ATR_PERIOD
    volume_sma_period: int = DEFAULT_VOLUME_SMA_PERIOD
    volume_ratio_min: Decimal = DEFAULT_VOLUME_RATIO_MIN
    pullback_ema_tolerance: Decimal = DEFAULT_PULLBACK_EMA_TOLERANCE
    stop_initial_atr_mult: Decimal = DEFAULT_STOP_INITIAL_ATR_MULT
    trail_atr_mult: Decimal = DEFAULT_TRAIL_ATR_MULT


class IndicatorSnapshot(BaseModel):
    """Computed indicators at evaluation index t (last closed daily candle)."""

    model_config = ConfigDict(frozen=True)

    evaluation_index: int
    ema20_daily: Decimal | None = None
    ema20_weekly: Decimal | None = None
    ema50_weekly: Decimal | None = None
    ema20_monthly: Decimal | None = None
    atr14_daily: Decimal | None = None
    volume_sma20: Decimal | None = None
    volume_ratio: Decimal | None = None
    high20: Decimal | None = None
    monthly_close: Decimal | None = None


class RegimeResult(BaseModel):
    """Monthly regime filter result."""

    model_config = ConfigDict(frozen=True)

    regime_long: bool
    monthly_close: Decimal | None = None
    ema20_monthly: Decimal | None = None
    reason_code: ReasonCode | None = None


class TrendResult(BaseModel):
    """Weekly trend confirmation result."""

    model_config = ConfigDict(frozen=True)

    trend_confirmed: bool
    ema20_weekly: Decimal | None = None
    ema50_weekly: Decimal | None = None
    reason_code: ReasonCode | None = None


class PullbackConditions(BaseModel):
    """Individual pullback conditions P1–P6."""

    model_config = ConfigDict(frozen=True)

    p1_close_above_ema: bool = False
    p2_low_touches_ema: bool = False
    p3_prior_close_above_ema: bool = False
    p4_regime_long: bool = False
    p5_trend_confirmed: bool = False
    p6_volume_ok: bool = False


class EntrySetupResult(BaseModel):
    """Breakout and pullback entry setup evaluation."""

    model_config = ConfigDict(frozen=True)

    breakout_entry: bool = False
    pullback_entry: bool = False
    breakout_price_condition: bool = False
    close_above_ema20: bool = False
    volume_ok: bool = False
    pullback_conditions: PullbackConditions = Field(default_factory=PullbackConditions)
    high20: Decimal | None = None
    ema_touch_upper: Decimal | None = None


class SignalIntent(BaseModel):
    """Order intent produced by strategy evaluation."""

    model_config = ConfigDict(frozen=True)

    kind: SignalIntentKind
    entry_type: EntryType | None = None
    entry_price: Decimal | None = None
    stop_initial: Decimal | None = None
    primary_reason_code: ReasonCode | None = None


class StrategyError(BaseModel):
    """Structured strategy error (fail-closed)."""

    model_config = ConfigDict(frozen=True)

    code: ReasonCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StrategyEvaluation(BaseModel):
    """Complete strategy evaluation output."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    evaluation_time: datetime
    strategy_version: str
    parameters: StrategyParameters
    monthly_regime: RegimeResult
    weekly_trend: TrendResult
    breakout_result: EntrySetupResult
    pullback_result: EntrySetupResult
    indicators: IndicatorSnapshot
    volume_ratio: Decimal | None = None
    atr: Decimal | None = None
    selected_entry_type: EntryType | None = None
    signal_intent: SignalIntent
    reason_codes: tuple[ReasonCode, ...] = Field(default_factory=tuple)
    data_quality_status: DataQualityStatus
    errors: tuple[StrategyError, ...] = Field(default_factory=tuple)


class TrailingStopState(BaseModel):
    """Trailing stop state for a open position (Strategy Spec §7)."""

    model_config = ConfigDict(frozen=True)

    entry_price: Decimal
    stop_initial: Decimal
    highest_close: Decimal
    trail_stop: Decimal
    effective_stop: Decimal

    @field_validator(
        "entry_price",
        "stop_initial",
        "highest_close",
        "trail_stop",
        "effective_stop",
        mode="before",
    )
    @classmethod
    def _ensure_decimal(cls, value: Decimal | str | float | int) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
