"""Tests for dataset manifest and content hashing (#77)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.content_hash import (
    HASH_ALGORITHM,
    canonical_decimal,
    derive_dataset_id,
    hash_normalized_candles,
    hash_raw_bytes,
)
from market_data.manifest import parse_manifest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle

FIXTURE = Path(__file__).parent / "fixtures" / "example_dataset_manifest.json"


def _candle(day: int) -> NormalizedCandle:
    open_time = datetime(2024, 1, day, 0, 0, tzinfo=UTC)
    close_time = datetime(2024, 1, day, 23, 59, 59, tzinfo=UTC)
    return NormalizedCandle(
        symbol=MarketSymbol.BTC,
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=close_time,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1000"),
        is_closed=True,
    )


def test_hash_algorithm_is_sha256() -> None:
    assert HASH_ALGORITHM == "sha256"


def test_canonical_decimal_no_drift() -> None:
    assert canonical_decimal(Decimal("1")) == canonical_decimal(Decimal("1.0"))
    assert canonical_decimal(Decimal("1.000000")) == "1"


def test_normalized_hash_stable_across_order() -> None:
    candles = (_candle(2), _candle(1), _candle(3))
    shuffled = (_candle(3), _candle(1), _candle(2))
    assert hash_normalized_candles(candles) == hash_normalized_candles(shuffled)


def test_normalized_hash_changes_with_content() -> None:
    a = hash_normalized_candles((_candle(1),))
    b = hash_normalized_candles((_candle(2),))
    assert a != b


def test_raw_hash() -> None:
    payload = b'{"candles":[]}'
    assert hash_raw_bytes(payload) == hash_raw_bytes(payload)
    assert hash_raw_bytes(payload) != hash_raw_bytes(b'{"candles":[1]}')


def test_derive_dataset_id_deterministic() -> None:
    h = "a" * 64
    assert derive_dataset_id(h, "1.0", "hyperliquid/mainnet") == derive_dataset_id(
        h, "1.0", "hyperliquid/mainnet"
    )


def test_parse_example_manifest_fixture() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = parse_manifest(data)
    assert manifest.dataset_id is not None
    assert manifest.symbols == (MarketSymbol.BTC,)
    assert manifest.with_dataset_id().dataset_id == manifest.dataset_id


def test_manifest_rejects_naive_timestamp() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["created_at"] = "2026-07-14T12:00:00"
    with pytest.raises(ValueError):
        parse_manifest(data)
