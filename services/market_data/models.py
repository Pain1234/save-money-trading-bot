"""Pydantic models for Market Data Service V1."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from strategy_engine.models import Candle, CandleSeries, Timeframe


class MarketSymbol(StrEnum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"


class MarketTimeframe(StrEnum):
    """Same canonical values as Strategy Engine ``Timeframe``."""

    DAILY = Timeframe.DAILY.value
    WEEKLY = Timeframe.WEEKLY.value
    MONTHLY = Timeframe.MONTHLY.value

    def to_strategy_timeframe(self) -> Timeframe:
        return Timeframe(self.value)


class DataQualityStatus(StrEnum):
    VALID = "VALID"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"
    DISCONNECTED = "DISCONNECTED"


class MarketDataReasonCode(StrEnum):
    MD_VALID = "MD_VALID"
    MD_STALE = "MD_STALE"
    MD_INCOMPLETE = "MD_INCOMPLETE"
    MD_INVALID = "MD_INVALID"
    MD_DISCONNECTED = "MD_DISCONNECTED"
    MD_DUPLICATE_IDENTICAL = "MD_DUPLICATE_IDENTICAL"
    MD_DUPLICATE_CONFLICT = "MD_DUPLICATE_CONFLICT"
    MD_GAP_DETECTED = "MD_GAP_DETECTED"
    MD_BACKFILL_FAILED = "MD_BACKFILL_FAILED"
    MD_OPEN_CANDLE_EXCLUDED = "MD_OPEN_CANDLE_EXCLUDED"
    MD_FUTURE_CANDLE = "MD_FUTURE_CANDLE"
    MD_INVALID_OHLC = "MD_INVALID_OHLC"
    MD_INVALID_VOLUME = "MD_INVALID_VOLUME"
    MD_INVALID_TIMEFRAME = "MD_INVALID_TIMEFRAME"
    MD_UNKNOWN_SYMBOL = "MD_UNKNOWN_SYMBOL"


class ConnectionStatus(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    SHUTDOWN = "SHUTDOWN"


class CandleKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    timeframe: MarketTimeframe
    open_time: datetime


class RawCandle(BaseModel):
    """Provider payload before normalization."""

    model_config = ConfigDict(frozen=True)

    provider_symbol: str
    timeframe: MarketTimeframe
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True


class NormalizedCandle(BaseModel):
    """Validated internal candle representation."""

    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    timeframe: MarketTimeframe
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool

    @property
    def key(self) -> CandleKey:
        return CandleKey(symbol=self.symbol, timeframe=self.timeframe, open_time=self.open_time)

    def to_strategy_candle(self) -> Candle:
        return Candle(
            symbol=self.symbol.value,
            timeframe=self.timeframe.to_strategy_timeframe(),
            open_time=self.open_time,
            close_time=self.close_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            is_closed=self.is_closed,
        )


class CandleBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    timeframe: MarketTimeframe
    candles: tuple[NormalizedCandle, ...] = Field(default_factory=tuple)
    evaluation_time: datetime


class CandleGap(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    timeframe: MarketTimeframe
    missing_open_time: datetime
    expected_close_time: datetime


class CandleConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: CandleKey
    existing: NormalizedCandle
    incoming: NormalizedCandle


class DataQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DataQualityStatus
    reason_codes: tuple[MarketDataReasonCode, ...] = Field(default_factory=tuple)
    gaps: tuple[CandleGap, ...] = Field(default_factory=tuple)
    conflicts: tuple[CandleConflict, ...] = Field(default_factory=tuple)
    missing_ranges: tuple[tuple[datetime, datetime], ...] = Field(default_factory=tuple)
    last_known_candle: NormalizedCandle | None = None
    expected_next_open: datetime | None = None
    evaluation_time: datetime
    messages: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return self.status == DataQualityStatus.VALID


class MarketDataHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    connection_status: ConnectionStatus
    last_heartbeat: datetime | None = None
    last_candle_time: datetime | None = None
    stale: bool = False
    report: DataQualityReport | None = None


class MarketDataSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    evaluation_time: datetime
    daily: tuple[NormalizedCandle, ...] = Field(default_factory=tuple)
    weekly: tuple[NormalizedCandle, ...] = Field(default_factory=tuple)
    monthly: tuple[NormalizedCandle, ...] = Field(default_factory=tuple)
    report: DataQualityReport


class StrategyDataBundle(BaseModel):
    """Closed candles ready for Strategy Engine consumption."""

    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    evaluation_time: datetime
    daily: CandleSeries
    weekly: CandleSeries
    monthly: CandleSeries
    report: DataQualityReport

    @property
    def is_usable(self) -> bool:
        return self.report.is_valid


class MarketDataError(Exception):
    """Fail-closed market data error."""

    def __init__(
        self,
        message: str,
        *,
        code: MarketDataReasonCode,
        report: DataQualityReport | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.report = report
