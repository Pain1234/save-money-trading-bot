"""Hyperliquid interval and candle parsing utilities."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from market_data.models import MarketSymbol, MarketTimeframe, RawCandle
from market_data.symbols import resolve_internal_symbol, to_provider_symbol
from market_data.timeframes import ensure_utc, is_candle_closed

HL_INTERVAL_TO_TIMEFRAME: dict[str, MarketTimeframe] = {
    "1d": MarketTimeframe.DAILY,
    "1w": MarketTimeframe.WEEKLY,
    "1M": MarketTimeframe.MONTHLY,
}

TIMEFRAME_TO_HL_INTERVAL: dict[MarketTimeframe, str] = {
    MarketTimeframe.DAILY: "1d",
    MarketTimeframe.WEEKLY: "1w",
    MarketTimeframe.MONTHLY: "1M",
}

_REQUIRED_STRICT_FIELDS = ("s", "i", "t", "T", "o", "h", "l", "c", "v", "n")
_REQUIRED_LEGACY_FIELDS = ("s", "t", "T", "o", "h", "l", "c")


def interval_for_timeframe(timeframe: MarketTimeframe) -> str:
    return TIMEFRAME_TO_HL_INTERVAL[timeframe]


def coin_for_symbol(symbol: MarketSymbol) -> str:
    return to_provider_symbol(symbol, provider="hyperliquid")


def _parse_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Non-finite decimal in field {field}")
        return value
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


def _epoch_ms_to_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, int):
        raise ValueError(f"Expected integer epoch millis in field {field}: {value!r}")
    if value < 1_000_000_000_000:
        raise ValueError(f"Expected epoch milliseconds in field {field}: {value}")
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


def _epoch_to_utc_legacy(value: Any, field: str) -> datetime:
    if value is None:
        raise ValueError(f"Missing timestamp field {field}")
    numeric = int(value)
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
    """Parse Hyperliquid candle payloads.

    Strict mode (network): requires official schema including ``n``,
    integer millisecond timestamps, exact symbol/interval match.
    Volume ``v`` is base-unit volume.
    Closure is derived from ``T`` and ``evaluation_time`` — no reliable ``closed`` field.
    """

    def parse_candle(
        self,
        payload: dict[str, Any],
        *,
        expected_coin: str | None = None,
        expected_interval: str | None = None,
        evaluation_time: datetime | None = None,
        strict: bool = False,
    ) -> RawCandle:
        required = _REQUIRED_STRICT_FIELDS if strict else _REQUIRED_LEGACY_FIELDS
        for field in required:
            if field not in payload:
                raise ValueError(f"Missing required Hyperliquid field: {field}")

        provider_symbol = str(payload["s"]).upper()
        resolve_internal_symbol(provider_symbol)
        if expected_coin is not None and provider_symbol != expected_coin.upper():
            raise ValueError(
                f"Symbol mismatch: expected {expected_coin}, got {provider_symbol}"
            )

        interval = str(payload["i"]) if "i" in payload else "1d"
        interval_key = interval if interval in HL_INTERVAL_TO_TIMEFRAME else interval.lower()
        if (
            interval_key not in HL_INTERVAL_TO_TIMEFRAME
            and interval not in HL_INTERVAL_TO_TIMEFRAME
        ):
            if interval.lower() in {"1day", "1week", "1month"}:
                interval_key = {"1day": "1d", "1week": "1w", "1month": "1M"}[interval.lower()]
            else:
                raise ValueError(f"Unsupported Hyperliquid interval: {interval}")
        if interval in HL_INTERVAL_TO_TIMEFRAME:
            interval_key = interval
        timeframe = HL_INTERVAL_TO_TIMEFRAME[interval_key]

        if expected_interval is not None and interval_key != expected_interval:
            raise ValueError(
                f"Interval mismatch: expected {expected_interval}, got {interval_key}"
            )

        if strict:
            open_time = _epoch_ms_to_utc(payload["t"], "t")
            close_time = _epoch_ms_to_utc(payload["T"], "T")
        else:
            open_time = _epoch_to_utc_legacy(payload["t"], "t")
            close_time = _epoch_to_utc_legacy(payload["T"], "T")

        if close_time <= open_time:
            raise ValueError("Close timestamp T must be after open timestamp t")

        if evaluation_time is not None:
            closed = is_candle_closed(close_time, ensure_utc(evaluation_time))
        elif "closed" in payload:
            closed = bool(payload["closed"])
        else:
            closed = False

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
            is_closed=closed,
        )

    def provider_symbol(self, symbol: MarketSymbol) -> str:
        return coin_for_symbol(symbol)
