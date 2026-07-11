"""Tests for trailing stop and stop-trigger lifecycle."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.config import PaperTradingConfig
from paper_trading.enums import PaperPositionStatus
from paper_trading.models import PaperPosition
from paper_trading.stops import StopLifecycleService

from tests.backtester.conftest import make_daily
from tests.paper_trading.conftest_execution import DEFAULT_CONSTRAINTS, utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _position() -> PaperPosition:
    return PaperPosition(
        position_id=uuid4(),
        symbol="BTC",
        status=PaperPositionStatus.OPEN,
        quantity=Decimal("0.1"),
        average_entry_price=Decimal("50000"),
        initial_stop=Decimal("48000"),
        current_stop=Decimal("48000"),
        highest_close_since_entry=Decimal("50000"),
        entry_atr14=Decimal("1000"),
        margin_reserved=Decimal("2500"),
        entry_intent_id=uuid4(),
        opened_at=utc_dt(2024, 1, 16),
    )


def test_trailing_stop_never_decreases() -> None:
    repo = MagicMock()
    position = _position()
    repo.get_open_position_for_symbol.return_value = position
    repo.insert_or_get_stop_event.return_value = (MagicMock(), False)
    service = StopLifecycleService(repo, config=_config())
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "50000", "49000", "47000", "48500")
    results = service.update_daily_trailing_stops(
        evaluation_time=utc_dt(2024, 1, 17),
        daily_candles={"BTC": candle},
        evaluation_atr_by_symbol={"BTC": Decimal("1000")},
        constraints_by_symbol={"BTC": DEFAULT_CONSTRAINTS},
        strategy_params=__import__("strategy_engine.models", fromlist=["StrategyParameters"]).StrategyParameters(),
    )
    assert results[0].updated is False


def test_gap_stop_triggers_close() -> None:
    repo = MagicMock()
    position = _position()
    repo.get_open_position_for_symbol.return_value = position
    row = MagicMock()
    row.status = PaperPositionStatus.OPEN.value
    repo.session.get.return_value = row
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    repo.get_wallet.return_value = MagicMock(cash=Decimal("100000"), total_realized_pnl=Decimal("0"))
    repo.get_open_positions.return_value = ()
    repo.insert_or_get_portfolio_snapshot.return_value = (MagicMock(), True)
    repo.insert_or_get_paper_fill.return_value = (MagicMock(), True)

    service = StopLifecycleService(repo, config=_config())
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "47000", "47500", "46500", "47200")
    results = service.process_stop_triggers_for_daily_candle(
        process_time=utc_dt(2024, 1, 17),
        daily_candles={"BTC": candle},
        constraints_by_symbol={"BTC": DEFAULT_CONSTRAINTS},
    )
    assert results[0].closed is True


def test_low_above_stop_no_exit() -> None:
    repo = MagicMock()
    position = _position()
    repo.get_open_position_for_symbol.return_value = position
    service = StopLifecycleService(repo, config=_config())
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "50000", "51000", "49000", "50500")
    results = service.process_stop_triggers_for_daily_candle(
        process_time=utc_dt(2024, 1, 17),
        daily_candles={"BTC": candle},
        constraints_by_symbol={"BTC": DEFAULT_CONSTRAINTS},
    )
    assert results[0].closed is False
