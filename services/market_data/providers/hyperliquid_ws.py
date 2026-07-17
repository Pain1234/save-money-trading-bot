"""Hyperliquid WebSocket live candle feed."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from market_data.config import HyperliquidPublicConfig, provider_subscriptions
from market_data.models import ConnectionStatus, RawCandle
from market_data.network.errors import (
    HyperliquidBufferOverflowError,
    HyperliquidWebSocketError,
)
from market_data.network.websocket_client import (
    ConnectFn,
    WebSocketConnection,
    default_websocket_connect,
    dumps_message,
    parse_ws_message,
)
from market_data.providers.hyperliquid import (
    HyperliquidCandleAdapter,
    coin_for_symbol,
    interval_for_timeframe,
)
from market_data.timeframes import ensure_utc, is_candle_closed

logger = logging.getLogger(__name__)

ClockFn = Callable[[], datetime]
SleepFn = Callable[[float], Awaitable[None]]


async def default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _sub_key(coin: str, interval: str) -> tuple[str, str]:
    return (coin.upper(), interval)


class HyperliquidWebSocketFeed:
    """Read-only Hyperliquid WebSocket candle feed with reconnect support."""

    def __init__(
        self,
        config: HyperliquidPublicConfig,
        *,
        connect_fn: ConnectFn = default_websocket_connect,
        adapter: HyperliquidCandleAdapter | None = None,
        clock: ClockFn | None = None,
        sleep: SleepFn = default_sleep,
    ) -> None:
        self._config = config
        self._connect_fn = connect_fn
        self._adapter = adapter or HyperliquidCandleAdapter()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._sleep = sleep
        self._conn: WebSocketConnection | None = None
        self._status = ConnectionStatus.DISCONNECTED
        self._expected_subs = {
            _sub_key(coin_for_symbol(sym), interval_for_timeframe(tf))
            for sym, tf in provider_subscriptions(config)
        }
        self._acked_subs: set[tuple[str, str]] = set()
        self._live_queue: asyncio.Queue[RawCandle] = asyncio.Queue()
        self._buffer: list[RawCandle] = []
        self._buffering = False
        self._last_message_time: datetime | None = None
        self._last_pong_time: datetime | None = None
        self._reconnect_count = 0
        self._consecutive_failures = 0
        self._reader_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._shutdown = False
        self._preview: dict[tuple[str, str, datetime], RawCandle] = {}
        self._subscribed: set[tuple[str, str]] = set()
        self._reconnect_lock = asyncio.Lock()
        self._background_error: str | None = None

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def subscriptions_expected(self) -> int:
        return len(self._expected_subs)

    @property
    def subscriptions_acknowledged(self) -> int:
        return len(self._acked_subs)

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def last_message_time(self) -> datetime | None:
        return self._last_message_time

    @property
    def last_pong_time(self) -> datetime | None:
        return self._last_pong_time

    @property
    def preview_candles(self) -> dict[tuple[str, str, datetime], RawCandle]:
        return dict(self._preview)

    @property
    def background_error(self) -> str | None:
        return self._background_error

    def begin_buffer(self) -> None:
        self._buffering = True
        self._buffer.clear()

    def end_buffer(self) -> tuple[RawCandle, ...]:
        self._buffering = False
        items = tuple(sorted(self._buffer, key=lambda c: c.open_time))
        self._buffer.clear()
        return items

    def discard_buffer(self) -> None:
        self._buffering = False
        self._buffer.clear()

    async def connect_and_subscribe(self) -> None:
        if self._shutdown:
            return
        self._status = ConnectionStatus.CONNECTING
        self._conn = await self._connect_fn(self._config.websocket_url)
        self._acked_subs.clear()
        self._subscribed.clear()
        for symbol, timeframe in provider_subscriptions(self._config):
            coin = coin_for_symbol(symbol)
            interval = interval_for_timeframe(timeframe)
            message = {
                "method": "subscribe",
                "subscription": {"type": "candle", "coin": coin, "interval": interval},
            }
            await self._conn.send(dumps_message(message))
            self._subscribed.add(_sub_key(coin, interval))

        deadline = time.monotonic() + self._config.subscription_ack_timeout_seconds
        while len(self._acked_subs) < len(self._expected_subs):
            if time.monotonic() > deadline:
                raise HyperliquidWebSocketError("Subscription acknowledgement timeout")
            remaining = max(0.01, deadline - time.monotonic())
            await self._read_once(timeout=min(0.5, remaining))

        self._status = ConnectionStatus.CONNECTED
        self._consecutive_failures = 0
        self._background_error = None
        await self._start_background_tasks()

    async def _start_background_tasks(self) -> None:
        await self._cancel_background_tasks()
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _cancel_background_tasks(self) -> None:
        for task in (self._reader_task, self._heartbeat_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._reader_task = None
        self._heartbeat_task = None

    async def _reader_loop(self) -> None:
        while not self._shutdown and self._conn is not None:
            try:
                await self._read_once()
            except asyncio.CancelledError:
                raise
            except HyperliquidWebSocketError as exc:
                self._background_error = str(exc)
                if not self._shutdown:
                    self._status = ConnectionStatus.RECONNECTING
                break
            except Exception as exc:
                self._background_error = str(exc)
                if not self._shutdown:
                    self._status = ConnectionStatus.RECONNECTING
                break

    async def _heartbeat_loop(self) -> None:
        while not self._shutdown and self._status == ConnectionStatus.CONNECTED:
            await self._sleep(self._config.heartbeat_interval_seconds)
            if self._shutdown or self._conn is None:
                break
            now = ensure_utc(self._clock())
            if self._last_pong_time is not None:
                elapsed = (now - self._last_pong_time).total_seconds()
                if elapsed > self._config.pong_timeout_seconds:
                    self._background_error = "pong timeout"
                    self._status = ConnectionStatus.RECONNECTING
                    break
            try:
                await self._conn.send(dumps_message({"method": "ping"}))
            except asyncio.CancelledError:
                raise
            except HyperliquidWebSocketError as exc:
                self._background_error = str(exc)
                self._status = ConnectionStatus.RECONNECTING
                break
            except Exception as exc:
                self._background_error = str(exc)
                self._status = ConnectionStatus.RECONNECTING
                break

    async def _read_once(self, *, timeout: float | None = None) -> None:
        if self._conn is None:
            raise HyperliquidWebSocketError("Not connected")
        try:
            if timeout is not None:
                text = await asyncio.wait_for(self._conn.recv(), timeout=timeout)
            else:
                text = await self._conn.recv()
        except TimeoutError:
            return
        self._last_message_time = ensure_utc(self._clock())
        self._last_pong_time = self._last_message_time
        payload = parse_ws_message(text)
        if not isinstance(payload, dict):
            return
        channel = payload.get("channel")
        if channel == "pong":
            self._last_pong_time = ensure_utc(self._clock())
            return
        if channel == "subscriptionResponse":
            self._handle_subscription_ack(payload)
            return
        if channel == "candle":
            self._handle_candle(payload)
            return

    def _handle_subscription_ack(self, payload: dict[str, Any]) -> None:
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        sub = data.get("subscription")
        if not isinstance(sub, dict):
            return
        if sub.get("type") != "candle":
            return
        coin = str(sub.get("coin", "")).upper()
        interval = str(sub.get("interval", ""))
        key = _sub_key(coin, interval)
        if key in self._expected_subs:
            self._acked_subs.add(key)

    def _handle_candle(self, payload: dict[str, Any]) -> None:
        data = payload.get("data")
        items: list[dict[str, Any]]
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = [i for i in data if isinstance(i, dict)]
        else:
            return

        evaluation_time = ensure_utc(self._clock())
        for item in items:
            coin = str(item.get("s", "")).upper()
            interval = str(item.get("i", ""))
            key = _sub_key(coin, interval)
            if key not in self._expected_subs:
                continue
            if self._buffering:
                if key not in self._subscribed:
                    continue
            elif key not in self._acked_subs:
                continue
            raw = self._adapter.parse_candle(
                item,
                expected_coin=coin,
                expected_interval=interval,
                evaluation_time=evaluation_time,
                strict=True,
            )
            preview_key = (raw.provider_symbol, raw.timeframe.value, raw.open_time)
            if not is_candle_closed(raw.close_time, evaluation_time):
                self._preview[preview_key] = raw
            if self._buffering:
                if len(self._buffer) >= self._config.reconnect_buffer_size:
                    raise HyperliquidBufferOverflowError("Reconnect buffer overflow")
                self._buffer.append(raw)
            else:
                self._live_queue.put_nowait(raw)

    async def drain_events(self, *, max_items: int = 1000) -> tuple[RawCandle, ...]:
        items: list[RawCandle] = []
        for _ in range(max_items):
            try:
                items.append(self._live_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return tuple(items)

    async def disconnect(self) -> None:
        if self._shutdown and self._conn is None:
            return
        self._shutdown = True
        self._status = ConnectionStatus.SHUTDOWN
        await self._cancel_background_tasks()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        self.discard_buffer()

    async def reconnect(self) -> None:
        if self._shutdown:
            return
        async with self._reconnect_lock:
            if self._shutdown:
                return
            self._reconnect_count += 1
            backoff_factor = 2 ** min(self._consecutive_failures, 5)
            delay = min(
                self._config.reconnect_initial_delay_seconds * backoff_factor,
                self._config.reconnect_max_delay_seconds,
            )
            await self._sleep(delay)
            self._consecutive_failures += 1
            await self._cancel_background_tasks()
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
            self._shutdown = False
            try:
                await self.connect_and_subscribe()
            except asyncio.CancelledError:
                if not self._shutdown:
                    # asyncio.timeout() cancels the in-flight handshake before
                    # translating cancellation into TimeoutError for the runtime.
                    # Keep the transport retryable for the next scheduler poll.
                    self._status = ConnectionStatus.RECONNECTING
                    self._background_error = "WebSocket reconnect cancelled"
                raise
            except Exception as exc:
                # connect_and_subscribe marks the feed CONNECTING before opening
                # the socket. A failed handshake (for example HTTP 502) must
                # return to RECONNECTING so the runtime retries on its next poll.
                self._status = ConnectionStatus.RECONNECTING
                self._background_error = str(exc)
                raise
