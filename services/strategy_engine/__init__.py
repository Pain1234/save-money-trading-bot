"""SAVE-MONEY BOT Strategy Engine V1 — Specification Freeze 1.0."""

from strategy_engine.engine import StrategyEngine
from strategy_engine.models import (
    Candle,
    CandleSeries,
    DataQualityStatus,
    EntrySetupResult,
    EntryType,
    IndicatorSnapshot,
    ReasonCode,
    RegimeResult,
    SignalIntent,
    SignalIntentKind,
    StrategyError,
    StrategyEvaluation,
    StrategyParameters,
    Timeframe,
    TrailingStopState,
    TrendResult,
)
from strategy_engine.stops import (
    compute_initial_stop,
    initialize_trailing_stop,
    update_trailing_stop,
)

__all__ = [
    "Candle",
    "CandleSeries",
    "DataQualityStatus",
    "EntrySetupResult",
    "EntryType",
    "IndicatorSnapshot",
    "ReasonCode",
    "RegimeResult",
    "SignalIntent",
    "SignalIntentKind",
    "StrategyEngine",
    "StrategyError",
    "StrategyEvaluation",
    "StrategyParameters",
    "Timeframe",
    "TrailingStopState",
    "TrendResult",
    "compute_initial_stop",
    "initialize_trailing_stop",
    "update_trailing_stop",
]

__version__ = "1.0.0"
