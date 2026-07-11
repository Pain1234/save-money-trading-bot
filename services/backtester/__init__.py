"""Event-driven backtester for Strategy Engine V1.0 and Risk Engine V1.0."""

from backtester.constants import BACKTESTER_VERSION, DEFAULT_SYMBOLS, INTRABAR_ASSUMPTION
from backtester.core_metadata import (
    CORE_ENGINE_METADATA,
    AccountingModel,
    AuditStatus,
    CoreEngineMetadata,
)
from backtester.engine import BacktestEngine
from backtester.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    DrawdownSnapshot,
    EquitySnapshot,
    ExecutionModel,
    FeeModel,
    FundingEvent,
    FundingModel,
    HistoricalDataBundle,
    PendingIntent,
    PortfolioState,
    RiskRejectionRecord,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPosition,
    SlippageModel,
)

__all__ = [
    "BACKTESTER_VERSION",
    "CORE_ENGINE_METADATA",
    "DEFAULT_SYMBOLS",
    "INTRABAR_ASSUMPTION",
    "AccountingModel",
    "AuditStatus",
    "CoreEngineMetadata",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestResult",
    "BacktestTrade",
    "DrawdownSnapshot",
    "EquitySnapshot",
    "ExecutionModel",
    "FeeModel",
    "FundingEvent",
    "FundingModel",
    "HistoricalDataBundle",
    "PendingIntent",
    "PortfolioState",
    "RiskRejectionRecord",
    "SimulatedFill",
    "SimulatedOrder",
    "SimulatedPosition",
    "SlippageModel",
]
