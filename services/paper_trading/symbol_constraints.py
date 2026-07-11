"""Symbol constraint resolution for production paper trading."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Protocol

from market_data.models import MarketSymbol
from market_data.providers.hyperliquid import coin_for_symbol
from risk_engine.models import SymbolConstraints

from paper_trading.config import ALLOWED_SYMBOLS, PaperTradingConfig

logger = logging.getLogger(__name__)


class SymbolConstraintsProvider(Protocol):
    def get(self, symbol: str) -> SymbolConstraints | None: ...

    def require(self, symbol: str) -> SymbolConstraints:
        constraints = self.get(symbol)
        if constraints is None:
            raise ValueError(f"missing SymbolConstraints for {symbol}")
        return constraints

    def get_all(self) -> dict[str, SymbolConstraints]: ...


def constraints_from_sz_decimals(sz_decimals: int) -> SymbolConstraints:
    """Hyperliquid perpetual tick/step sizing from ``szDecimals``."""
    if sz_decimals < 0 or sz_decimals > 6:
        raise ValueError(f"invalid sz_decimals: {sz_decimals}")
    quantity_step = Decimal(1).scaleb(-sz_decimals)
    price_tick = Decimal(1).scaleb(-(6 - sz_decimals))
    return SymbolConstraints(
        quantity_step=quantity_step,
        minimum_quantity=quantity_step,
        minimum_notional=Decimal("10"),
        price_tick_size=price_tick,
    )


class StaticSymbolConstraintsProvider:
    """Fixed constraints map (tests and explicit production overrides)."""

    def __init__(self, constraints: dict[str, SymbolConstraints]) -> None:
        unknown = set(constraints) - ALLOWED_SYMBOLS
        if unknown:
            raise ValueError(f"unsupported symbols in constraints: {sorted(unknown)}")
        self._constraints = dict(constraints)

    def get(self, symbol: str) -> SymbolConstraints | None:
        return self._constraints.get(symbol)

    def require(self, symbol: str) -> SymbolConstraints:
        constraints = self.get(symbol)
        if constraints is None:
            raise ValueError(f"missing SymbolConstraints for {symbol}")
        return constraints

    def get_all(self) -> dict[str, SymbolConstraints]:
        return dict(self._constraints)


class HyperliquidSymbolConstraintsProvider:
    """Resolve constraints from validated Hyperliquid meta ``szDecimals``."""

    def __init__(self, sz_decimals_by_coin: dict[str, int]) -> None:
        self._by_symbol: dict[str, SymbolConstraints] = {}
        for symbol in ALLOWED_SYMBOLS:
            coin = coin_for_symbol(MarketSymbol(symbol))
            sz = sz_decimals_by_coin.get(coin.upper())
            if sz is None:
                continue
            self._by_symbol[symbol] = constraints_from_sz_decimals(sz)

    def get(self, symbol: str) -> SymbolConstraints | None:
        return self._by_symbol.get(symbol)

    def require(self, symbol: str) -> SymbolConstraints:
        constraints = self.get(symbol)
        if constraints is None:
            raise ValueError(f"missing SymbolConstraints for {symbol}")
        return constraints

    def get_all(self) -> dict[str, SymbolConstraints]:
        return dict(self._by_symbol)


def load_constraints_provider(config: PaperTradingConfig) -> SymbolConstraintsProvider | None:
    """Build constraints provider from env override, else defer to runtime meta."""
    import os

    raw = os.environ.get("PAPER_SYMBOL_CONSTRAINTS_JSON")
    if raw:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("PAPER_SYMBOL_CONSTRAINTS_JSON must be a JSON object")
        parsed: dict[str, SymbolConstraints] = {}
        for symbol, item in payload.items():
            if symbol not in ALLOWED_SYMBOLS:
                raise ValueError(f"unsupported symbol in constraints JSON: {symbol}")
            if not isinstance(item, dict):
                raise ValueError(f"constraints for {symbol} must be an object")
            parsed[symbol] = SymbolConstraints.model_validate(item)
        missing = ALLOWED_SYMBOLS - set(parsed)
        if missing:
            raise ValueError(f"PAPER_SYMBOL_CONSTRAINTS_JSON missing symbols: {sorted(missing)}")
        logger.info("symbol_constraints_loaded_from_env")
        return StaticSymbolConstraintsProvider(parsed)
    _ = config
    return None
