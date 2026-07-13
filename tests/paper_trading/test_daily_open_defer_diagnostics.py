"""Tests for daily open defer diagnostic logging."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from market_data.models import MarketSymbol
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService
from paper_trading.clock import FixedClock
from paper_trading.market_event_errors import RetryableContextNotReady
from paper_trading.models import PaperExecutionConfig
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.scheduler_context_diagnostics import (
    DailyOpenDeferSnapshot,
    build_daily_open_defer_snapshot,
    format_daily_open_defer_log,
)
from paper_trading.symbol_constraints import StaticSymbolConstraintsProvider
from risk_engine.models import RiskParameters
from strategy_engine.constants import (
    MIN_DAILY_CANDLES,
    MIN_MONTHLY_CANDLES,
    MIN_WEEKLY_CANDLES,
)

from tests.market_data.conftest import make_daily_series, make_monthly, make_weekly
from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.integration.lifecycle_helpers import btc_eth_sol_constraints


def test_format_daily_open_defer_log_includes_required_fields_in_message() -> None:
    snapshot = DailyOpenDeferSnapshot(
        symbol="BTC",
        error_code=RetryableContextNotReady.code,
        reason='strategy bundle not usable for BTC at 2024-01-16T00:00:00+00:00',
        daily_count=364,
        weekly_count=51,
        monthly_count=11,
        daily_minimum=MIN_DAILY_CANDLES,
        weekly_minimum=MIN_WEEKLY_CANDLES,
        monthly_minimum=MIN_MONTHLY_CANDLES,
        bundle_usable=False,
        atr14_present=False,
        market_data_ready=True,
        prior_eval_time=utc_dt(2024, 1, 16),
        evaluation_time=utc_dt(2024, 1, 16, 1),
        input_candle_count=21,
        first_input_open_time=utc_dt(2023, 12, 26),
        last_input_open_time=utc_dt(2024, 1, 15),
        last_input_is_closed=True,
        true_range_count=20,
        valid_true_range_count=20,
        atr_window=14,
        indicator_reason_code="ATR_NOT_AVAILABLE",
    )

    message = format_daily_open_defer_log(snapshot)

    assert message.startswith("daily_open_deferred ")
    assert "symbol=BTC" in message
    assert f"error_code={RetryableContextNotReady.code}" in message
    assert 'reason="strategy bundle not usable for BTC' in message
    assert f"daily_candles=364/{MIN_DAILY_CANDLES}" in message
    assert f"weekly_candles=51/{MIN_WEEKLY_CANDLES}" in message
    assert f"monthly_candles=11/{MIN_MONTHLY_CANDLES}" in message
    assert "bundle_usable=no" in message
    assert "atr14=no" in message
    assert "market_data_ready=yes" in message
    assert "prior_eval_time=" in message
    assert "evaluation_time=" in message
    assert "input_candle_count=21" in message
    assert "first_input_open_time=" in message
    assert "last_input_open_time=" in message
    assert "last_input_is_closed=yes" in message
    assert "true_range_count=20" in message
    assert "valid_true_range_count=20" in message
    assert "atr_window=14" in message
    assert "indicator_reason_code=ATR_NOT_AVAILABLE" in message
    assert "open=" not in message
    assert "high=" not in message
    assert "low=" not in message
    assert "close=" not in message
    assert "postgresql://" not in message.lower()
    assert "password" not in message.lower()


def test_format_daily_open_defer_log_truncates_unsafe_reason() -> None:
    snapshot = DailyOpenDeferSnapshot(
        symbol="ETH",
        error_code=RetryableContextNotReady.code,
        reason="x" * 300,
        daily_count=0,
        weekly_count=0,
        monthly_count=0,
        daily_minimum=MIN_DAILY_CANDLES,
        weekly_minimum=MIN_WEEKLY_CANDLES,
        monthly_minimum=MIN_MONTHLY_CANDLES,
        bundle_usable=False,
        atr14_present=False,
        market_data_ready=False,
    )

    message = format_daily_open_defer_log(snapshot)

    assert "reason=\"" in message
    assert "xxx" in message
    assert "x" * 300 not in message


def _context_builder(
    repo: InMemoryCandleRepository,
    *,
    market_data_ready: bool,
) -> ProductionContextBuilder:
    runtime_repo = MagicMock()
    runtime = MagicMock()
    runtime.status = "READY"
    runtime.kill_switch = False
    runtime.paused = False
    runtime_repo.get_runtime_state.return_value = runtime

    market_data = MarketDataService(repo)
    config = MagicMock()
    config.symbols = ("BTC",)

    return ProductionContextBuilder(
        market_data=market_data,
        repository=runtime_repo,
        config=config,
        constraints=StaticSymbolConstraintsProvider(btc_eth_sol_constraints()),
        clock=FixedClock(utc_dt(2024, 6, 1)),
        execution_config=PaperExecutionConfig(
            fee_rate=Decimal("0.0005"),
            slippage_bps=Decimal("5"),
            max_leverage=Decimal("2"),
        ),
        risk_params=RiskParameters(
            risk_per_trade_pct=Decimal("0.005"),
            max_portfolio_risk_pct=Decimal("0.02"),
            max_leverage=Decimal("2"),
        ),
        market_data_ready=lambda: market_data_ready,
    )


def test_describe_daily_open_defer_reports_insufficient_native_monthly_history() -> None:
    """One-year native backfill pattern: daily/weekly ok, monthly below minimum."""
    dailies = make_daily_series(364, start=utc_dt(2023, 1, 16))
    weeklies = tuple(
        make_weekly(MarketSymbol.BTC, utc_dt(2023, 1, 16) + timedelta(weeks=i))
        for i in range(51)
    )
    monthlies = tuple(make_monthly(MarketSymbol.BTC, 2023, month) for month in range(2, 13))
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert_many(weeklies)
    repo.upsert_many(monthlies)

    eval_time = utc_dt(2024, 1, 16, 1)
    prior_eval_time = utc_dt(2024, 1, 16)
    builder = _context_builder(repo, market_data_ready=True)
    error = RetryableContextNotReady(
        f"strategy bundle not usable for BTC at {prior_eval_time.isoformat()}"
    )

    message = builder.describe_daily_open_defer(
        "BTC",
        open_candle=None,
        prior_eval_time=prior_eval_time,
        evaluation_time=eval_time,
        error=error,
    )

    assert "monthly_candles=11/20" in message
    assert "daily_candles=364/21" in message
    assert "weekly_candles=51/50" in message
    assert "bundle_usable=no" in message
    assert "atr14=no" in message
    assert "market_data_ready=yes" in message


def test_build_daily_open_defer_snapshot_without_prior_eval_time() -> None:
    snapshot = build_daily_open_defer_snapshot(
        symbol="SOL",
        error=RetryableContextNotReady("daily open candle missing at processing time"),
        market_data_service=MagicMock(),
        strategy_params=MagicMock(),
        market_data_ready=False,
        prior_eval_time=None,
        evaluation_time=utc_dt(2024, 1, 16, 1),
        build_strategy_bundle=MagicMock(),
    )

    assert snapshot.daily_count == 0
    assert snapshot.bundle_usable is False
    assert snapshot.market_data_ready is False


def test_daily_open_defer_warning_record_contains_full_message_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logging.getLogger("paper_trading.market_events").disabled = False
    caplog.set_level(logging.WARNING, logger="paper_trading.market_events")

    dailies = make_daily_series(364, start=utc_dt(2023, 1, 16))
    weeklies = tuple(
        make_weekly(MarketSymbol.BTC, utc_dt(2023, 1, 16) + timedelta(weeks=i))
        for i in range(51)
    )
    monthlies = tuple(make_monthly(MarketSymbol.BTC, 2023, month) for month in range(2, 13))
    repo = InMemoryCandleRepository()
    repo.upsert_many(dailies)
    repo.upsert_many(weeklies)
    repo.upsert_many(monthlies)

    builder = _context_builder(repo, market_data_ready=True)
    prior_eval_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    error = RetryableContextNotReady(
        f"strategy bundle not usable for BTC at {prior_eval_time.isoformat()}"
    )
    message = builder.describe_daily_open_defer(
        "BTC",
        open_candle=None,
        prior_eval_time=prior_eval_time,
        evaluation_time=eval_time,
        error=error,
    )

    logging.getLogger("paper_trading.market_events").warning(message)

    assert len(caplog.records) == 1
    assert caplog.records[0].message == message
    assert "monthly_candles=11/20" in caplog.records[0].message
    assert caplog.records[0].message.startswith("daily_open_deferred ")
