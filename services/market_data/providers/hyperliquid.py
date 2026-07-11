"""Hyperliquid public market data adapter — network-free parsing layer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from market_data.models import MarketSymbol, MarketTimeframe, RawCandle
from market_data.symbols import resolve_internal_symbol, to_provider_symbol

_HL_TIMEFRAME_MAP = {
    "1d": MarketTimeframe.DAILY,
    "1day": MarketTimeframe.DAILY,
    "1w": MarketTimeframe.WEEKLY,
    "1week": MarketTimeframe.WEEKLY,
    "1m": MarketTimeframe.MONTHLY,
    "1month": MarketTimeframe.MONTHLY,
}

_REQUIRED_FIELDS = ("s", "t", "T", "o", "h", "l", "c")


def _parse_decimal(value: Any, field: str) -> Decimal:
    text = str(value)
    lowered = text.lower()
    if lowered in {"nan", "inf", "-inf", "infinity", "-infinity"}:
        raise ValueError(f"Non-finite decimal in field {field}: {text}")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal in field {field}: {text}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Non-finite decimal in field {field}: {text}")
    return parsed


def _epoch_to_utc(value: Any, field: str) -> datetime:
    if value is None:
        raise ValueError(f"Missing timestamp field {field}")
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timestamp in field {field}: {value}") from exc

    if numeric >= 1_000_000_000_000:
        seconds = numeric / 1000.0
    elif numeric >= 1_000_000_000:
        seconds = float(numeric)
    else:
        raise ValueError(
            f"Ambiguous timestamp unit in field {field}: {numeric} "
            "(expected epoch seconds or milliseconds)"
        )
    return datetime.fromtimestamp(seconds, tz=UTC)


class HyperliquidCandleAdapter:
    """Parse Hyperliquid-style candle payloads without performing HTTP calls.

    Timestamp semantics:
    - ``t`` is candle open time, ``T`` is candle close time.
    - Values >= 1e12 are treated as epoch milliseconds; values >= 1e9 as seconds.
    - ``closed`` defaults to False when omitted (open/in-progress candle).
    """

    def parse_candle(self, payload: dict[str, Any]) -> RawCandle:
        for field in _REQUIRED_FIELDS:
            if field not in payload:
                raise ValueError(f"Missing required Hyperliquid field: {field}")

        provider_symbol = str(payload["s"]).upper()
        resolve_internal_symbol(provider_symbol)
        interval = str(payload.get("i", "1d")).lower()
        if interval not in _HL_TIMEFRAME_MAP:
            raise ValueError(f"Unsupported Hyperliquid interval: {interval}")
        timeframe = _HL_TIMEFRAME_MAP[interval]
        open_time = _epoch_to_utc(payload["t"], "t")
        close_time = _epoch_to_utc(payload["T"], "T")
        return RawCandle(
            provider_symbol=provider_symbol,
            timeframe=timeframe,
            open_time=open_time,
            close_time=close_time,
            open=_parse_decimal(payload["o"], "o"),
            high=_parse_decimal(payload["h"], "h"),
            low=_parse_decimal(payload["l"], "l"),
            close=_parse_decimal(payload["c"], "c"),
            volume=_parse_decimal(payload.get("v", "0"), "v"),
            is_closed=bool(payload["closed"]) if "closed" in payload else False,
        )

    def provider_symbol(self, symbol: MarketSymbol) -> str:
        return to_provider_symbol(symbol, provider="hyperliquid")
