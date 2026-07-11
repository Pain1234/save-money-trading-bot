"""Decimal-safe JSON parsing."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def decimal_parse_float(value: str) -> Decimal:
    lowered = value.lower()
    if lowered in {"nan", "inf", "-inf", "infinity", "-infinity"}:
        raise ValueError(f"Non-finite JSON number: {value}")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError(f"Non-finite JSON number: {value}")
    return parsed


def loads_decimal(text: str) -> Any:
    return json.loads(text, parse_float=decimal_parse_float)
