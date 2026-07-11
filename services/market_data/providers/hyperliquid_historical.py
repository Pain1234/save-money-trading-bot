"""Hyperliquid candleSnapshot HTTP provider with pagination."""

from __future__ import annotations

import logging
from datetime import datetime

from market_data.config import HyperliquidPublicConfig
from market_data.models import MarketSymbol, MarketTimeframe, RawCandle
from market_data.network.errors import HyperliquidPaginationIncompleteError, HyperliquidParseError
from market_data.network.http_client import HyperliquidHttpClient
from market_data.providers.hyperliquid import (
    HyperliquidCandleAdapter,
    coin_for_symbol,
    interval_for_timeframe,
)
from market_data.timeframes import ensure_utc

logger = logging.getLogger(__name__)


def _to_epoch_ms(dt: datetime) -> int:
    dt = ensure_utc(dt)
    return int(dt.timestamp() * 1000)


class HyperliquidHistoricalProvider:
    """Fetch historical candles via POST /info candleSnapshot."""

    def __init__(
        self,
        client: HyperliquidHttpClient,
        config: HyperliquidPublicConfig,
        *,
        adapter: HyperliquidCandleAdapter | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._adapter = adapter or HyperliquidCandleAdapter()

    async def fetch_candles(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        evaluation_time: datetime,
    ) -> tuple[RawCandle, ...]:
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)
        evaluation_time = ensure_utc(evaluation_time)
        if start_time > end_time:
            raise ValueError("start_time must be <= end_time")

        coin = coin_for_symbol(symbol)
        interval = interval_for_timeframe(timeframe)
        start_ms = _to_epoch_ms(start_time)
        end_ms = _to_epoch_ms(end_time)

        all_candles: list[RawCandle] = []
        seen_keys: set[tuple[int, int]] = set()
        cursor = start_ms
        last_progress_ms: int | None = None
        stagnant_pages = 0
        pagination_complete = False

        for page in range(self._config.max_pagination_pages):
            body = {
                "type": "candleSnapshot",
                "req": {
                    "coin": coin,
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                },
            }
            payload = await self._client.post_info(
                body, request_id=f"snapshot-{coin}-{interval}-{page}"
            )
            if not isinstance(payload, list):
                raise HyperliquidParseError("candleSnapshot response must be a list")

            if not payload:
                pagination_complete = True
                break

            page_candles: list[RawCandle] = []
            for item in payload:
                if not isinstance(item, dict):
                    raise HyperliquidParseError("candleSnapshot item must be an object")
                raw = self._adapter.parse_candle(
                    item,
                    expected_coin=coin,
                    expected_interval=interval,
                    evaluation_time=evaluation_time,
                    strict=True,
                )
                open_ms = _to_epoch_ms(raw.open_time)
                if open_ms > end_ms:
                    raise HyperliquidParseError(
                        f"candleSnapshot candle open time {open_ms} after "
                        f"requested end {end_ms}"
                    )
                if open_ms < start_ms:
                    continue
                key = (open_ms, _to_epoch_ms(raw.close_time))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                page_candles.append(raw)

            page_candles.sort(key=lambda c: c.open_time)
            if not page_candles:
                pagination_complete = True
                break

            all_candles.extend(page_candles)
            last = page_candles[-1]
            last_ms = _to_epoch_ms(last.open_time)
            if last_progress_ms is not None and last_ms <= last_progress_ms:
                stagnant_pages += 1
                if stagnant_pages >= 2:
                    raise HyperliquidPaginationIncompleteError(
                        f"pagination stagnant at timestamp {last_ms} for {coin}/{interval}"
                    )
            else:
                stagnant_pages = 0
            last_progress_ms = last_ms

            if last_ms >= end_ms or len(payload) < self._config.max_candles_per_snapshot:
                pagination_complete = True
                break

            cursor = _to_epoch_ms(last.close_time) + 1
            if cursor > end_ms:
                pagination_complete = True
                break

        if not pagination_complete:
            raise HyperliquidPaginationIncompleteError(
                f"pagination incomplete for {coin}/{interval}: "
                f"cursor={cursor}, end_ms={end_ms}, pages={self._config.max_pagination_pages}"
            )

        all_candles.sort(key=lambda c: c.open_time)
        return tuple(all_candles)

    async def fetch_history(
        self,
        symbol: MarketSymbol,
        timeframe: MarketTimeframe,
        start: datetime,
        end: datetime,
        *,
        limit: int = 500,
        evaluation_time: datetime | None = None,
    ) -> tuple[RawCandle, ...]:
        eval_time = ensure_utc(evaluation_time or end)
        candles = await self.fetch_candles(symbol, timeframe, start, end, eval_time)
        return candles[:limit]
