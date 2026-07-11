"""Controllable market-data runtime for integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from market_data.config import HyperliquidNetwork
from market_data.ingest import ingest_live_raw, ingest_raw_batch
from market_data.models import ConnectionStatus, MarketSymbol, RawCandle
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService
from market_data.timeframes import ensure_utc


@dataclass
class ControlledMarketDataRuntime:
    """Scriptable market-data double backing a real MarketDataService."""

    service: MarketDataService
    _ready: bool = False
    _connected: bool = True
    _closed: bool = False
    _pending: list[RawCandle] = field(default_factory=list)
    _network: HyperliquidNetwork = HyperliquidNetwork.TESTNET

    @classmethod
    def create(
        cls, *, network: HyperliquidNetwork = HyperliquidNetwork.TESTNET
    ) -> ControlledMarketDataRuntime:
        repo = InMemoryCandleRepository()
        service = MarketDataService(repo)
        return cls(service=service, _network=network)

    @property
    def repository(self) -> InMemoryCandleRepository:
        repo = self.service.repository
        assert isinstance(repo, InMemoryCandleRepository)
        return repo

    def enqueue_raw(self, *raws: RawCandle) -> None:
        self._pending.extend(raws)

    def ingest_history(
        self,
        raws: tuple[RawCandle, ...],
        evaluation_time: datetime,
    ) -> None:
        ingest_raw_batch(self.repository, raws, ensure_utc(evaluation_time))

    async def start(self, evaluation_time: datetime) -> None:
        self._ready = True
        self._connected = True
        self._closed = False

    async def aclose(self) -> None:
        self._closed = True
        self._ready = False
        self._connected = False

    async def process_live(self, evaluation_time: datetime) -> int:
        evaluation_time = ensure_utc(evaluation_time)
        batch = tuple(self._pending)
        self._pending.clear()
        if not batch:
            return 0
        result = ingest_live_raw(self.repository, batch, evaluation_time)
        return result.inserted

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if not connected:
            self._ready = False

    def set_ready(self, ready: bool) -> None:
        self._ready = ready

    def status(self, evaluation_time: datetime) -> object:
        from market_data.runtime import HyperliquidRuntimeStatus

        return HyperliquidRuntimeStatus(
            network=self._network,
            websocket_status=(
                ConnectionStatus.CONNECTED
                if self._connected and not self._closed
                else ConnectionStatus.DISCONNECTED
            ),
            subscriptions_expected=9,
            subscriptions_acknowledged=9 if self._connected and not self._closed else 0,
            readiness=self._ready and self._connected and not self._closed,
        )

    @property
    def closed(self) -> bool:
        return self._closed


def raw_daily(
    symbol: str,
    open_time: datetime,
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: str = "1000",
    is_closed: bool = True,
) -> RawCandle:
    from market_data.models import MarketTimeframe
    from market_data.providers.hyperliquid import coin_for_symbol
    from market_data.timeframes import daily_close

    open_time = ensure_utc(open_time)
    close_time = daily_close(open_time)
    return RawCandle(
        provider_symbol=coin_for_symbol(MarketSymbol(symbol)),
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=close_time,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
        is_closed=is_closed,
    )
