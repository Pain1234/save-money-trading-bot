"""Hyperliquid public adapter runtime orchestration."""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig, all_subscriptions
from market_data.gaps import detect_gaps
from market_data.ingest import ingest_live_raw, ingest_raw_batch
from market_data.models import (
    CandleConflict,
    ConnectionStatus,
    DataQualityReport,
    DataQualityStatus,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    RawCandle,
)
from market_data.network.http_client import HyperliquidHttpClient
from market_data.providers.hyperliquid import coin_for_symbol
from market_data.providers.hyperliquid_historical import HyperliquidHistoricalProvider
from market_data.providers.hyperliquid_meta import HyperliquidMetaCache, fetch_perpetual_meta
from market_data.providers.hyperliquid_ws import HyperliquidWebSocketFeed
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService
from market_data.timeframes import ensure_utc
from market_data.validation import validate_series

logger = logging.getLogger(__name__)


class SeriesRuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: MarketSymbol
    timeframe: MarketTimeframe
    quality_status: DataQualityStatus
    last_closed_candle: NormalizedCandle | None = None
    last_preview_candle: RawCandle | None = None


class HyperliquidRuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    network: HyperliquidNetwork
    http_status: str = "idle"
    websocket_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    subscriptions_expected: int = 0
    subscriptions_acknowledged: int = 0
    last_message_time: datetime | None = None
    last_pong_time: datetime | None = None
    reconnect_count: int = 0
    consecutive_failures: int = 0
    last_successful_backfill: datetime | None = None
    series: tuple[SeriesRuntimeStatus, ...] = Field(default_factory=tuple)
    last_error: str | None = None
    readiness: bool = False


class HyperliquidMarketDataRuntime:
    """Async runtime integrating Hyperliquid HTTP/WS with MarketDataService."""

    def __init__(
        self,
        service: MarketDataService,
        config: HyperliquidPublicConfig,
        *,
        http_client: HyperliquidHttpClient | None = None,
        ws_feed: HyperliquidWebSocketFeed | None = None,
    ) -> None:
        self._service = service
        self._config = config
        self._http = http_client or HyperliquidHttpClient(config)
        self._historical = HyperliquidHistoricalProvider(self._http, config)
        self._ws = ws_feed or HyperliquidWebSocketFeed(config)
        self._meta_cache = HyperliquidMetaCache(ttl_seconds=config.meta_cache_ttl_seconds)
        self._last_backfill: datetime | None = None
        self._last_error: str | None = None
        self._initial_backfill_done = False
        self._meta_ok = False

    @property
    def repository(self) -> InMemoryCandleRepository:
        repo = self._service.repository
        assert isinstance(repo, InMemoryCandleRepository)
        return repo

    async def aclose(self) -> None:
        await self._ws.disconnect()
        await self._http.aclose()

    async def backfill_symbol(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        evaluation_time: datetime,
    ) -> DataQualityReport:
        evaluation_time = ensure_utc(evaluation_time)
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)
        await fetch_perpetual_meta(self._http, self._config, cache=self._meta_cache)
        self._meta_ok = True
        raws = await self._historical.fetch_candles(
            symbol, timeframe, start_time, end_time, evaluation_time
        )
        ingest_raw_batch(self.repository, raws, evaluation_time)
        closed = self.repository.get_closed_before(symbol, timeframe, evaluation_time)
        gaps = detect_gaps(closed, symbol, timeframe, evaluation_time)
        report = validate_series(
            closed,
            symbol,
            timeframe,
            evaluation_time,
            gaps=gaps,
            conflicts=_repo_conflicts(self.repository, symbol, timeframe),
        )
        self._last_backfill = evaluation_time
        logger.info(
            "hyperliquid_backfill",
            extra={
                "event_type": "backfill",
                "symbol": symbol.value,
                "timeframe": timeframe.value,
                "status": report.status.value,
            },
        )
        return report

    async def start(self, evaluation_time: datetime) -> None:
        evaluation_time = ensure_utc(evaluation_time)
        await fetch_perpetual_meta(self._http, self._config, cache=self._meta_cache)
        self._meta_ok = True
        await self._ws.connect_and_subscribe()
        self._ws.begin_buffer()
        for symbol, timeframe in all_subscriptions(self._config):
            latest = self.repository.get_latest(symbol, timeframe)
            if latest is None:
                start = evaluation_time.replace(year=evaluation_time.year - 1)
            else:
                start = latest.open_time
            await self.backfill_symbol(symbol, timeframe, start, evaluation_time, evaluation_time)
        buffered = self._ws.end_buffer()
        ingest_live_raw(self.repository, buffered, evaluation_time)
        self._initial_backfill_done = True

    async def process_live(self, evaluation_time: datetime) -> int:
        evaluation_time = ensure_utc(evaluation_time)
        events = await self._ws.drain_events()
        result = ingest_live_raw(self.repository, events, evaluation_time)
        return result.inserted

    async def reconnect(self, evaluation_time: datetime) -> None:
        evaluation_time = ensure_utc(evaluation_time)
        self._ws.begin_buffer()
        await self._ws.reconnect()
        for symbol, timeframe in all_subscriptions(self._config):
            latest = self.repository.get_latest(symbol, timeframe)
            if latest is None:
                continue
            await self.backfill_symbol(
                symbol,
                timeframe,
                latest.open_time,
                evaluation_time,
                evaluation_time,
            )
        buffered = self._ws.end_buffer()
        ingest_live_raw(self.repository, buffered, evaluation_time)

    def status(self, evaluation_time: datetime) -> HyperliquidRuntimeStatus:
        evaluation_time = ensure_utc(evaluation_time)
        series_status: list[SeriesRuntimeStatus] = []
        unresolved_conflicts = self.repository.conflicts
        all_valid = True
        for symbol, timeframe in all_subscriptions(self._config):
            closed = self.repository.get_closed_before(symbol, timeframe, evaluation_time)
            gaps = detect_gaps(closed, symbol, timeframe, evaluation_time)
            report = validate_series(
                closed,
                symbol,
                timeframe,
                evaluation_time,
                gaps=gaps,
                conflicts=_repo_conflicts(self.repository, symbol, timeframe),
            )
            if report.status in (DataQualityStatus.INVALID, DataQualityStatus.DISCONNECTED):
                all_valid = False
            preview = None
            for key, raw in self._ws.preview_candles.items():
                if key[0] == coin_for_symbol(symbol) and key[1] == timeframe.value:
                    preview = raw
            series_status.append(
                SeriesRuntimeStatus(
                    symbol=symbol,
                    timeframe=timeframe,
                    quality_status=report.status,
                    last_closed_candle=closed[-1] if closed else None,
                    last_preview_candle=preview,
                )
            )

        readiness = (
            self._meta_ok
            and self._ws.subscriptions_acknowledged >= self._ws.subscriptions_expected
            and self._initial_backfill_done
            and not unresolved_conflicts
            and all_valid
            and self._ws.status == ConnectionStatus.CONNECTED
        )
        return HyperliquidRuntimeStatus(
            network=self._config.network,
            http_status="ready" if self._meta_ok else "idle",
            websocket_status=self._ws.status,
            subscriptions_expected=self._ws.subscriptions_expected,
            subscriptions_acknowledged=self._ws.subscriptions_acknowledged,
            last_message_time=self._ws.last_message_time,
            last_pong_time=self._ws.last_pong_time,
            reconnect_count=self._ws.reconnect_count,
            last_successful_backfill=self._last_backfill,
            series=tuple(series_status),
            last_error=self._last_error,
            readiness=readiness,
        )


def _repo_conflicts(
    repository: InMemoryCandleRepository,
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
) -> tuple[CandleConflict, ...]:
    return tuple(
        c
        for c in repository.conflicts
        if c.key.symbol == symbol and c.key.timeframe == timeframe
    )
