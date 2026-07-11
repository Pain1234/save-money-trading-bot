"""Market Data Service V1 — read-only validated candles for Strategy Engine."""

from market_data.bundle import get_strategy_bundle
from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from market_data.constants import MARKET_DATA_VERSION
from market_data.live import LiveFeedProcessor
from market_data.models import (
    CandleBatch,
    CandleGap,
    CandleKey,
    ConnectionStatus,
    DataQualityReport,
    DataQualityStatus,
    MarketDataError,
    MarketDataHealth,
    MarketDataReasonCode,
    MarketDataSnapshot,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    RawCandle,
    StrategyDataBundle,
)
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime, HyperliquidRuntimeStatus
from market_data.service import MarketDataService

__all__ = [
    "MARKET_DATA_VERSION",
    "CandleBatch",
    "CandleGap",
    "CandleKey",
    "ConnectionStatus",
    "DataQualityReport",
    "DataQualityStatus",
    "InMemoryCandleRepository",
    "LiveFeedProcessor",
    "MarketDataError",
    "MarketDataHealth",
    "MarketDataReasonCode",
    "MarketDataService",
    "MarketDataSnapshot",
    "MarketSymbol",
    "MarketTimeframe",
    "NormalizedCandle",
    "RawCandle",
    "HyperliquidMarketDataRuntime",
    "HyperliquidNetwork",
    "HyperliquidPublicConfig",
    "HyperliquidRuntimeStatus",
    "StrategyDataBundle",
    "get_strategy_bundle",
]
