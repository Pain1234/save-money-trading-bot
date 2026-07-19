"""Shared ExperimentSpec helpers for research tests (#363)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from research.symbol_constraints import hyperliquid_mainnet_v1_pins


def with_sealed_symbol_constraints(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``raw`` with HL mainnet v1 pins for its symbols."""
    out = deepcopy(raw)
    symbols = out.get("symbols") or ["BTC"]
    if not isinstance(symbols, list):
        symbols = ["BTC"]
    out["symbol_constraints"] = hyperliquid_mainnet_v1_pins(
        [str(s) for s in symbols]
    )
    return out
