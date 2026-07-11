# ruff: noqa: E402
"""Shared fixtures for risk engine tests."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from risk_engine.models import (
    AccountState,
    PositionState,
    SymbolConstraints,
    TradeProposal,
)
from strategy_engine.models import SignalIntentKind

DEFAULT_CONSTRAINTS = SymbolConstraints(
    quantity_step=Decimal("0.001"),
    minimum_quantity=Decimal("0.001"),
    minimum_notional=Decimal("10"),
    price_tick_size=Decimal("0.01"),
)


def make_account(
    equity: str = "100000",
    margin: str = "50000",
) -> AccountState:
    return AccountState(
        equity_usd=Decimal(equity),
        available_margin_usd=Decimal(margin),
    )


def make_long_proposal(
    symbol: str = "BTC",
    entry: str = "95000",
    stop: str = "89000",
    intent_id: str = "intent-1",
) -> TradeProposal:
    return TradeProposal(
        symbol=symbol,
        entry_price=Decimal(entry),
        stop_price=Decimal(stop),
        client_intent_id=intent_id,
        signal_intent_kind=SignalIntentKind.LONG_ENTRY,
        strategy_approved=True,
    )


def make_position(
    symbol: str,
    size: str,
    entry: str,
    stop_initial: str,
    trail: str | None = None,
    mark: str | None = None,
) -> PositionState:
    entry_d = Decimal(entry)
    return PositionState(
        symbol=symbol,
        entry_price=entry_d,
        position_size=Decimal(size),
        stop_initial=Decimal(stop_initial),
        trail_stop=Decimal(trail or stop_initial),
        mark_price=Decimal(mark or entry),
    )
