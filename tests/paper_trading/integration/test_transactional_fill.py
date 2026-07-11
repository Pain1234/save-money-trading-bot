"""PostgreSQL transactional fill tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from paper_trading.enums import PaperSide, SignalType, TradeIntentStatus
from paper_trading.execution import MissingSymbolConstraintsError, PaperFillService
from paper_trading.models import PaperExecutionConfig, TradeIntent
from paper_trading.repository import PaperTradingRepository
from risk_engine.models import RiskParameters
from strategy_engine.models import StrategyParameters

from tests.paper_trading.conftest import requires_postgres


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


@requires_postgres
def test_fill_without_constraints_raises(db_session) -> None:
    repo = PaperTradingRepository(db_session)
    service = PaperFillService(repo)
    intent = TradeIntent(
        intent_id=uuid4(),
        idempotency_key="k",
        symbol="BTC",
        side=PaperSide.LONG,
        signal_type=SignalType.BREAKOUT,
        signal_time=_utc(2024, 1, 15),
        scheduled_fill_time=_utc(2024, 1, 16),
        requested_entry=Decimal("50000"),
        requested_stop=Decimal("48000"),
        status=TradeIntentStatus.SCHEDULED,
        strategy_evaluation_id=uuid4(),
        created_at=_utc(2024, 1, 15),
        updated_at=_utc(2024, 1, 15),
    )
    with pytest.raises(MissingSymbolConstraintsError):
        service.execute_scheduled_paper_fill(
            intent=intent,
            atr14=Decimal("1000"),
            open_ref=Decimal("50000"),
            candle_open_time=_utc(2024, 1, 16),
            constraints=None,  # type: ignore[arg-type]
            strategy_params=StrategyParameters(),
            risk_params=RiskParameters(),
            execution_config=PaperExecutionConfig(
                fee_rate=Decimal("0.0005"),
                slippage_bps=Decimal("5"),
                max_leverage=Decimal("2"),
            ),
            day_candles={},
            prior_closes={},
            processed_intent_ids=frozenset(),
        )
