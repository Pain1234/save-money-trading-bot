"""Hyperliquid perpetual metadata fetch and validation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from market_data.config import HyperliquidPublicConfig
from market_data.models import MarketSymbol
from market_data.network.errors import HyperliquidParseError
from market_data.network.http_client import HyperliquidHttpClient
from market_data.providers.hyperliquid import coin_for_symbol
from market_data.timeframes import ensure_utc

logger = logging.getLogger(__name__)

ClockFn = Callable[[], datetime]


class HyperliquidMetaCache:
    def __init__(
        self,
        *,
        ttl_seconds: float,
        clock: ClockFn | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._cached_at: datetime | None = None
        self._universe: frozenset[str] | None = None

    def get(self) -> frozenset[str] | None:
        if self._universe is None or self._cached_at is None:
            return None
        now = ensure_utc(self._clock())
        if (now - self._cached_at).total_seconds() > self._ttl:
            return None
        return self._universe

    def set(self, universe: frozenset[str]) -> None:
        self._universe = universe
        self._cached_at = ensure_utc(self._clock())


def _parse_universe(payload: Any) -> frozenset[str]:
    if not isinstance(payload, dict):
        raise HyperliquidParseError("Meta response must be an object")
    universe = payload.get("universe")
    if not isinstance(universe, list):
        raise HyperliquidParseError("Meta response missing universe list")
    names: set[str] = set()
    for item in universe:
        if not isinstance(item, dict):
            raise HyperliquidParseError("Meta universe entry must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise HyperliquidParseError("Meta universe entry missing name")
        names.add(name.upper())
    if not names:
        raise HyperliquidParseError("Meta universe is empty")
    return frozenset(names)


async def fetch_perpetual_meta(
    client: HyperliquidHttpClient,
    config: HyperliquidPublicConfig,
    *,
    cache: HyperliquidMetaCache | None = None,
) -> frozenset[str]:
    """Fetch and validate perpetual universe contains configured symbols."""
    if cache is not None:
        cached = cache.get()
        if cached is not None:
            _validate_required_symbols(cached, config.symbols)
            return cached

    payload = await client.post_info({"type": "meta"}, request_id="meta")
    universe = _parse_universe(payload)
    required = {coin_for_symbol(sym) for sym in config.symbols}
    missing = required - universe
    if missing:
        raise HyperliquidParseError(
            f"Required perpetual symbols missing from meta: {sorted(missing)}"
        )
    if cache is not None:
        cache.set(universe)
    logger.info(
        "hyperliquid_meta_ok",
        extra={"event_type": "meta", "network": config.network.value, "status": "ok"},
    )
    return universe


def _validate_required_symbols(universe: frozenset[str], symbols: tuple[MarketSymbol, ...]) -> None:
    required = {coin_for_symbol(sym) for sym in symbols}
    missing = required - universe
    if missing:
        raise HyperliquidParseError(
            f"Required perpetual symbols missing from meta: {sorted(missing)}"
        )
