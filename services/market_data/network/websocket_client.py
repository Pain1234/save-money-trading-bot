"""WebSocket connection abstractions for Hyperliquid live feed."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from market_data.network.errors import HyperliquidWebSocketError
from market_data.network.json_utils import loads_decimal

ConnectFn = Callable[[str], Awaitable["WebSocketConnection"]]


class WebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str: ...

    async def close(self) -> None: ...


class FakeWebSocketConnection:
    """Deterministic WebSocket fake for unit tests."""

    def __init__(
        self,
        incoming: asyncio.Queue[str | None],
        *,
        outgoing: list[str] | None = None,
        closed: asyncio.Event | None = None,
    ) -> None:
        self._incoming = incoming
        self.outgoing = outgoing if outgoing is not None else []
        self._closed = closed or asyncio.Event()

    async def send(self, message: str) -> None:
        if self._closed.is_set():
            raise HyperliquidWebSocketError("WebSocket closed")
        self.outgoing.append(message)

    async def recv(self) -> str:
        if self._closed.is_set():
            raise HyperliquidWebSocketError("WebSocket closed")
        item = await self._incoming.get()
        if item is None:
            self._closed.set()
            raise HyperliquidWebSocketError("WebSocket disconnected by peer")
        return item

    async def close(self) -> None:
        self._closed.set()
        await self._incoming.put(None)


async def default_websocket_connect(url: str) -> WebSocketConnection:
    import websockets

    conn = await websockets.connect(url)
    return _WebsocketsWrapper(conn)


class _WebsocketsWrapper:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def send(self, message: str) -> None:
        await self._conn.send(message)

    async def recv(self) -> str:
        msg = await self._conn.recv()
        return str(msg)

    async def close(self) -> None:
        await self._conn.close()


def dumps_message(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def parse_ws_message(text: str) -> Any:
    return loads_decimal(text)
