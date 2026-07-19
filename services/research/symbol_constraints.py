"""Sealed Hyperliquid symbol constraints for research ExperimentSpecs (#363).

Pins exchange sizing metadata into Spec identity so P5 runs cannot silently
monkeypatch constraints outside the sealed configuration.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from risk_engine.models import SymbolConstraints

# Pinned Hyperliquid mainnet szDecimals for BTC/ETH/SOL (research freeze set).
# Changing these values requires a new constraint_set_version + dedicated issue.
HYPERLIQUID_MAINNET_CONSTRAINT_SET_VERSION = "hl-mainnet-szdecimals-v1"
HYPERLIQUID_MAINNET_SZ_DECIMALS_V1: dict[str, int] = {
    "BTC": 5,
    "ETH": 4,
    "SOL": 2,
}
_MINIMUM_NOTIONAL = Decimal("10")


def constraints_from_sz_decimals(sz_decimals: int) -> SymbolConstraints:
    """Hyperliquid perpetual tick/step sizing from ``szDecimals``."""
    if sz_decimals < 0 or sz_decimals > 6:
        raise ValueError(f"invalid sz_decimals: {sz_decimals}")
    quantity_step = Decimal(1).scaleb(-sz_decimals)
    price_tick = Decimal(1).scaleb(-(6 - sz_decimals))
    return SymbolConstraints(
        quantity_step=quantity_step,
        minimum_quantity=quantity_step,
        minimum_notional=_MINIMUM_NOTIONAL,
        price_tick_size=price_tick,
    )


def pin_dict_from_constraints(constraints: SymbolConstraints) -> dict[str, str]:
    """JSON-safe decimal strings for ExperimentSpec.symbol_constraints entries."""
    return {
        "quantity_step": str(constraints.quantity_step),
        "minimum_quantity": str(constraints.minimum_quantity),
        "minimum_notional": str(constraints.minimum_notional),
        "price_tick_size": str(constraints.price_tick_size),
    }


def hyperliquid_mainnet_v1_pins(
    symbols: tuple[str, ...] | list[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Sealed HL mainnet constraint pins for the requested symbols."""
    wanted = tuple(symbols) if symbols is not None else tuple(
        HYPERLIQUID_MAINNET_SZ_DECIMALS_V1
    )
    out: dict[str, dict[str, str]] = {}
    for sym in wanted:
        key = str(sym)
        if key not in HYPERLIQUID_MAINNET_SZ_DECIMALS_V1:
            raise ValueError(f"no sealed HL mainnet szDecimals for {key!r}")
        out[key] = pin_dict_from_constraints(
            constraints_from_sz_decimals(HYPERLIQUID_MAINNET_SZ_DECIMALS_V1[key])
        )
    return out


def compute_constraint_set_content_hash(pins: dict[str, dict[str, str]]) -> str:
    """SHA-256 over canonical pin map (sorted keys)."""
    payload = json.dumps(pins, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


HYPERLIQUID_MAINNET_V1_PINS = hyperliquid_mainnet_v1_pins()
HYPERLIQUID_MAINNET_V1_CONTENT_HASH = compute_constraint_set_content_hash(
    HYPERLIQUID_MAINNET_V1_PINS
)


def symbol_constraints_for_backtest(
    pins: dict[str, dict[str, str]] | dict[str, object],
) -> dict[str, SymbolConstraints]:
    """Convert Spec pin map into BacktestConfig.symbol_constraints."""
    out: dict[str, SymbolConstraints] = {}
    for sym, raw in pins.items():
        if not isinstance(raw, dict):
            raise ValueError(f"symbol_constraints[{sym!r}] must be an object")
        out[str(sym)] = SymbolConstraints(
            quantity_step=Decimal(str(raw["quantity_step"])),
            minimum_quantity=Decimal(str(raw["minimum_quantity"])),
            minimum_notional=Decimal(str(raw["minimum_notional"])),
            price_tick_size=Decimal(str(raw["price_tick_size"])),
        )
    return out


__all__ = [
    "HYPERLIQUID_MAINNET_CONSTRAINT_SET_VERSION",
    "HYPERLIQUID_MAINNET_SZ_DECIMALS_V1",
    "HYPERLIQUID_MAINNET_V1_CONTENT_HASH",
    "HYPERLIQUID_MAINNET_V1_PINS",
    "compute_constraint_set_content_hash",
    "constraints_from_sz_decimals",
    "hyperliquid_mainnet_v1_pins",
    "pin_dict_from_constraints",
    "symbol_constraints_for_backtest",
]
