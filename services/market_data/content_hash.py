"""Canonical content hashing for dataset manifests (Issue #77)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from market_data.models import NormalizedCandle

HASH_ALGORITHM = "sha256"

# Metadata fields excluded from normalized content hash.
EXCLUDED_FROM_CONTENT_HASH = frozenset(
    {
        "created_at",
        "import_job_id",
        "dataset_id",
        "content_hash",
        "raw_content_hash",
        "quality_status",
        "known_issues",
        "allow_quality_warnings",
        "quality_report",
    }
)


def canonical_decimal(value: Decimal) -> str:
    """Fixed-scale decimal string (no exponent drift)."""
    normalized = value.normalize()
    return format(normalized, "f")


def canonical_timestamp(value: datetime) -> str:
    """UTC ISO-8601 with microsecond precision."""
    if value.tzinfo is None:
        msg = "timestamp must be timezone-aware UTC"
        raise ValueError(msg)
    from datetime import UTC

    as_utc = value.astimezone(UTC)
    return as_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_candle_row(candle: NormalizedCandle) -> dict[str, str]:
    return {
        "symbol": candle.symbol.value,
        "timeframe": candle.timeframe.value,
        "open_time": canonical_timestamp(candle.open_time),
        "close_time": canonical_timestamp(candle.close_time),
        "open": canonical_decimal(candle.open),
        "high": canonical_decimal(candle.high),
        "low": canonical_decimal(candle.low),
        "close": canonical_decimal(candle.close),
        "volume": canonical_decimal(candle.volume),
        "is_closed": "true" if candle.is_closed else "false",
    }


def sort_candle_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda r: (r["symbol"], r["timeframe"], r["open_time"]),
    )


def hash_normalized_candles(candles: tuple[NormalizedCandle, ...]) -> str:
    """SHA-256 over canonical JSON of sorted normalized candle rows."""
    rows = sort_candle_rows([canonical_candle_row(c) for c in candles])
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_raw_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def hash_aggregate_candles(candles: tuple[NormalizedCandle, ...]) -> str:
    """Separate hash for derived aggregate layer."""
    return hash_normalized_candles(candles)


def derive_dataset_id(content_hash: str, schema_version: str, source: str) -> str:
    """Deterministic dataset id from content identity and schema."""
    seed = f"{schema_version}:{source}:{content_hash}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def strip_hash_metadata(manifest_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in manifest_dict.items() if k not in EXCLUDED_FROM_CONTENT_HASH}
