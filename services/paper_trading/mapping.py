"""Map market data quality to risk engine market data status."""

from __future__ import annotations

from market_data.models import DataQualityStatus
from risk_engine.models import MarketDataStatus


def map_data_quality_to_market_data_status(status: DataQualityStatus) -> MarketDataStatus:
    if status == DataQualityStatus.VALID:
        return MarketDataStatus.OK
    if status == DataQualityStatus.STALE:
        return MarketDataStatus.STALE
    if status == DataQualityStatus.INCOMPLETE:
        return MarketDataStatus.INCOMPLETE
    return MarketDataStatus.INVALID
