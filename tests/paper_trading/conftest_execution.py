# ruff: noqa: E402
"""Shared fixtures for paper trading execution tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

_SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from paper_trading.enums import PaperSide, SignalType, TradeIntentStatus
from paper_trading.models import PaperExecutionConfig, TradeIntent
from risk_engine.models import SymbolConstraints

UTC = UTC

DEFAULT_CONSTRAINTS = SymbolConstraints(
    quantity_step=Decimal("0.001"),
    minimum_quantity=Decimal("0.001"),
    minimum_notional=Decimal("10"),
    price_tick_size=Decimal("0.01"),
)

EXECUTION_CONFIG = PaperExecutionConfig(
    fee_rate=Decimal("0.0005"),
    slippage_bps=Decimal("5"),
    max_leverage=Decimal("2"),
)


def utc_dt(y: int, m: int, d: int, h: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, second, tzinfo=UTC)


def make_trade_intent(
    *,
    symbol: str = "BTC",
    entry: Decimal = Decimal("50000"),
    stop: Decimal = Decimal("48000"),
    signal_time: datetime | None = None,
) -> TradeIntent:
    signal_time = signal_time or utc_dt(2024, 1, 15, 0, 0, 5)
    intent_id = uuid4()
    return TradeIntent(
        intent_id=intent_id,
        idempotency_key=f"{symbol}:1.0:2024-01-15T00:00:05Z:BREAKOUT",
        symbol=symbol,
        side=PaperSide.LONG,
        signal_type=SignalType.BREAKOUT,
        signal_time=signal_time,
        scheduled_fill_time=utc_dt(2024, 1, 16),
        requested_entry=entry,
        requested_stop=stop,
        status=TradeIntentStatus.SCHEDULED,
        strategy_evaluation_id=uuid4(),
        created_at=signal_time,
        updated_at=signal_time,
    )
