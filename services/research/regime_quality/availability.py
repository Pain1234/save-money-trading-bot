"""NOT_AVAILABLE / missing-metric helpers for regime quality (#287)."""

from __future__ import annotations

from typing import Any

NOT_AVAILABLE = "NOT_AVAILABLE"


def na() -> str:
    return NOT_AVAILABLE


def is_na(value: Any) -> bool:
    return value == NOT_AVAILABLE


def decimal_or_na(value: object | None) -> str | None:
    """Serialize Decimal-like values as strings; None → NOT_AVAILABLE."""
    if value is None:
        return NOT_AVAILABLE
    return format(value, "f") if hasattr(value, "__format__") else str(value)
