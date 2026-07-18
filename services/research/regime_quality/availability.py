"""NOT_AVAILABLE / missing-metric helpers for regime quality (#287)."""

from __future__ import annotations

from decimal import Decimal

NOT_AVAILABLE = "NOT_AVAILABLE"


def na() -> str:
    return NOT_AVAILABLE


def is_na(value: object) -> bool:
    return value == NOT_AVAILABLE


def decimal_or_na(value: object | None) -> str:
    """Serialize Decimal-like values as strings; None → NOT_AVAILABLE."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
