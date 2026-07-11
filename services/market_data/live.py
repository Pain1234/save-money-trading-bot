"""Live candle feed processing with reconnect and stale detection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from market_data.constants import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
    DEFAULT_STALE_THRESHOLD_SECONDS,
)
from market_data.models import (
    ConnectionStatus,
    DataQualityReport,
    DataQualityStatus,
    MarketDataHealth,
    MarketDataReasonCode,
    MarketSymbol,
    MarketTimeframe,
    NormalizedCandle,
    RawCandle,
)
from market_data.normalize import normalize_raw_candle
from market_data.providers.in_memory import InMemoryLiveProvider
from market_data.service import MarketDataService
from market_data.stale import is_candle_data_stale
from market_data.timeframes import ensure_utc
from market_data.validation import candles_equal, validate_candle_structure, validate_raw_candle

SleepFn = Callable[[float], None]
ClockFn = Callable[[], datetime]


class LiveFeedProcessor:
    """Process live candles with heartbeat, stale detection, and reconnect."""

    def __init__(
        self,
        service: MarketDataService,
        live_provider: InMemoryLiveProvider,
        *,
        symbols: tuple[MarketSymbol, ...] = (MarketSymbol.BTC,),
        stale_threshold_seconds: int = DEFAULT_STALE_THRESHOLD_SECONDS,
        heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        max_backoff_seconds: int = DEFAULT_MAX_BACKOFF_SECONDS,
        clock: ClockFn | None = None,
        sleep: SleepFn | None = None,
    ) -> None:
        self._service = service
        self._live = live_provider
        self._symbols = symbols
        self._stale_threshold = stale_threshold_seconds
        self._heartbeat_interval = heartbeat_interval_seconds
        self._max_backoff = max_backoff_seconds
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._sleep = sleep or (lambda _: None)
        self._status = ConnectionStatus.DISCONNECTED
        self._last_heartbeat: datetime | None = None
        self._last_candle_time: datetime | None = None
        self._last_daily_candle: NormalizedCandle | None = None
        self._backoff_attempts = 0
        self._processed_identical_keys: set[tuple[str, str, datetime]] = set()
        self._shutdown = False

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    def connect(self) -> None:
        self._status = ConnectionStatus.CONNECTING
        self._live.connect()
        self._live.subscribe(self._symbols)
        self._status = ConnectionStatus.CONNECTED
        self._backoff_attempts = 0
        self._touch_heartbeat()

    def disconnect(self) -> None:
        self._shutdown = True
        self._live.disconnect()
        self._status = ConnectionStatus.SHUTDOWN

    def _touch_heartbeat(self) -> None:
        self._last_heartbeat = ensure_utc(self._clock())

    def heartbeat(self) -> None:
        self._touch_heartbeat()

    def is_transport_stale(self, evaluation_time: datetime | None = None) -> bool:
        now = ensure_utc(evaluation_time or self._clock())
        if self._last_heartbeat is None:
            return True
        return (now - self._last_heartbeat).total_seconds() > self._stale_threshold

    def is_stale(self, evaluation_time: datetime | None = None) -> bool:
        now = ensure_utc(evaluation_time or self._clock())
        if self.is_transport_stale(now):
            return True
        return is_candle_data_stale(self._last_daily_candle, now)

    def health(self, evaluation_time: datetime | None = None) -> MarketDataHealth:
        now = ensure_utc(evaluation_time or self._clock())
        transport_stale = self.is_transport_stale(now)
        candle_stale = is_candle_data_stale(self._last_daily_candle, now)
        stale = transport_stale or candle_stale
        report: DataQualityReport | None = None
        if self._status == ConnectionStatus.DISCONNECTED:
            report = DataQualityReport(
                status=DataQualityStatus.DISCONNECTED,
                reason_codes=(MarketDataReasonCode.MD_DISCONNECTED,),
                evaluation_time=now,
            )
        elif stale:
            report = DataQualityReport(
                status=DataQualityStatus.STALE,
                reason_codes=(MarketDataReasonCode.MD_STALE,),
                evaluation_time=now,
            )
        return MarketDataHealth(
            connection_status=self._status,
            last_heartbeat=self._last_heartbeat,
            last_candle_time=self._last_candle_time,
            stale=stale,
            report=report,
        )

    def _event_key(self, raw: RawCandle) -> tuple[str, str, datetime]:
        return (raw.provider_symbol, raw.timeframe.value, raw.open_time)

    def process_events(self, evaluation_time: datetime) -> int:
        evaluation_time = ensure_utc(evaluation_time)
        if self._shutdown:
            return 0
        if self._status not in (ConnectionStatus.CONNECTED, ConnectionStatus.RECONNECTING):
            return 0
        processed = 0
        for raw in self._live.poll_events():
            key = self._event_key(raw)
            if validate_raw_candle(raw):
                continue
            normalized = normalize_raw_candle(raw, evaluation_time)
            if validate_candle_structure(normalized):
                continue

            existing = self._service.repository.get_range(
                normalized.symbol, normalized.timeframe
            )
            match = next((c for c in existing if c.open_time == normalized.open_time), None)
            if match is not None:
                if candles_equal(match, normalized):
                    self._processed_identical_keys.add(key)
                    continue
            elif key in self._processed_identical_keys:
                continue

            result = self._service.store_normalized((normalized,), evaluation_time)
            if result.inserted == 0 and not result.conflicts:
                if result.identical_skipped:
                    self._processed_identical_keys.add(key)
                continue

            if result.inserted or result.conflicts:
                self._last_candle_time = normalized.close_time
                if normalized.timeframe == MarketTimeframe.DAILY:
                    self._last_daily_candle = normalized
                processed += 1
        self._touch_heartbeat()
        return processed

    def reconnect_once(self, evaluation_time: datetime) -> None:
        evaluation_time = ensure_utc(evaluation_time)
        if self._shutdown:
            return
        self._status = ConnectionStatus.RECONNECTING
        delay = min(2**self._backoff_attempts, self._max_backoff)
        self._sleep(float(delay))
        self._backoff_attempts += 1
        self._live.disconnect()
        self._live.connect()
        self._live.subscribe(self._symbols)
        self._status = ConnectionStatus.CONNECTED
        self._backoff_attempts = 0
        self._touch_heartbeat()
        for symbol in self._symbols:
            for tf in (
                MarketTimeframe.DAILY,
                MarketTimeframe.WEEKLY,
                MarketTimeframe.MONTHLY,
            ):
                self._service.attempt_backfill(symbol, tf, evaluation_time)
        self.process_events(evaluation_time)

    def graceful_shutdown(self) -> None:
        self.disconnect()
