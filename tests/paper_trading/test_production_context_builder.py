"""Regression tests for ProductionContextBuilder readiness wiring."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from market_data.models import MarketSymbol
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService
from paper_trading.clock import FixedClock
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperExecutionConfig
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.symbol_constraints import StaticSymbolConstraintsProvider
from risk_engine.models import RiskParameters

from tests.market_data.conftest import make_daily, make_daily_series, make_monthly, make_weekly
from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.integration.lifecycle_helpers import btc_eth_sol_constraints


def _builder(*, market_data_ready, paused: bool = False):
    repo = MagicMock()
    runtime = MagicMock()
    runtime.status = RuntimeStatus.READY
    runtime.kill_switch = False
    runtime.paused = paused
    repo.get_runtime_state.return_value = runtime

    bundle = MagicMock()
    bundle.is_usable = True
    market_data = MagicMock()
    market_data.build_strategy_bundle.return_value = bundle

    config = MagicMock()
    config.symbols = ("BTC",)

    execution_config = PaperExecutionConfig(
        fee_rate=Decimal("0.0005"),
        slippage_bps=Decimal("5"),
        max_leverage=Decimal("2"),
    )
    risk_params = RiskParameters(
        risk_per_trade_pct=Decimal("0.005"),
        max_portfolio_risk_pct=Decimal("0.02"),
        max_leverage=Decimal("2"),
    )

    return (
        ProductionContextBuilder(
            market_data=market_data,
            repository=repo,
            config=config,
            constraints=StaticSymbolConstraintsProvider(btc_eth_sol_constraints()),
            clock=FixedClock(utc_dt(2024, 6, 1)),
            execution_config=execution_config,
            risk_params=risk_params,
            market_data_ready=market_data_ready,
        ),
        utc_dt(2024, 6, 1),
    )


def test_production_context_builder_requires_market_data_ready_source() -> None:
    repo = MagicMock()
    config = MagicMock()
    with pytest.raises(ValueError, match="market_data_ready source is required"):
        ProductionContextBuilder(
            market_data=MagicMock(),
            repository=repo,
            config=config,
            constraints=StaticSymbolConstraintsProvider(btc_eth_sol_constraints()),
            clock=FixedClock(utc_dt(2024, 1, 1)),
            execution_config=PaperExecutionConfig(
                fee_rate=Decimal("0.0005"),
                slippage_bps=Decimal("5"),
                max_leverage=Decimal("2"),
            ),
        )


def test_runtime_false_blocks_market_data_ready_gate() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: False)
    context = builder.build_evaluation_context("BTC", eval_time)
    assert context is not None
    entry_gates = context["symbols"]["BTC"]["entry_gates"]
    assert entry_gates.market_data_ready is False


def test_runtime_true_allows_existing_evaluation_path() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: True)
    context = builder.build_evaluation_context("BTC", eval_time)
    assert context is not None
    entry_gates = context["symbols"]["BTC"]["entry_gates"]
    assert entry_gates.market_data_ready is True


def test_persisted_pause_blocks_production_entry_gate() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: True, paused=True)

    context = builder.build_evaluation_context("BTC", eval_time)

    entry_gates = context["symbols"]["BTC"]["entry_gates"]
    assert entry_gates.entry_ready is False
    assert entry_gates.paused is True


def test_stub_boolean_readiness_is_supported_via_lambda() -> None:
    builder, eval_time = _builder(market_data_ready=lambda: True)
    assert builder.build_evaluation_context("BTC", eval_time) is not None


def _production_daily_open_builder() -> tuple[
    ProductionContextBuilder,
    InMemoryCandleRepository,
    object,
]:
    repository = InMemoryCandleRepository()
    daily_start = utc_dt(2024, 7, 14)
    dailies = make_daily_series(729, start=daily_start)
    weeklies = tuple(
        make_weekly(MarketSymbol.BTC, daily_start + timedelta(weeks=index))
        for index in range(104)
    )
    monthlies = tuple(
        make_monthly(MarketSymbol.BTC, 2024 + (6 + index) // 12, (6 + index) % 12 + 1)
        for index in range(24)
    )
    repository.upsert_many((*dailies, *weeklies, *monthlies))
    open_candle = make_daily(
        MarketSymbol.BTC,
        utc_dt(2026, 7, 13),
        is_closed=False,
    )
    repository.upsert(open_candle)

    runtime_repo = MagicMock()
    runtime = MagicMock()
    runtime.status = RuntimeStatus.READY
    runtime.kill_switch = False
    runtime.paused = False
    runtime_repo.get_runtime_state.return_value = runtime
    config = MagicMock()
    config.symbols = ("BTC",)
    builder = ProductionContextBuilder(
        market_data=MarketDataService(repository),
        repository=runtime_repo,
        config=config,
        constraints=StaticSymbolConstraintsProvider(btc_eth_sol_constraints()),
        clock=FixedClock(utc_dt(2026, 7, 13)),
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
        market_data_ready=lambda: True,
    )
    return builder, repository, open_candle


def test_729_closed_daily_candles_produce_atr14_at_daily_open() -> None:
    builder, _, open_candle = _production_daily_open_builder()

    fill_contexts, _ = builder.build_open_contexts(
        "BTC", open_candle, utc_dt(2026, 7, 13)
    )

    assert fill_contexts["BTC"].atr14 > 0


def test_daily_open_atr_uses_only_candles_closed_before_exact_open() -> None:
    builder, _, open_candle = _production_daily_open_builder()
    first, _ = builder.build_open_contexts("BTC", open_candle, open_candle.open_time)
    changed_open = open_candle.model_copy(
        update={
            "open": Decimal("1000000"),
            "high": Decimal("1000000"),
            "low": Decimal("1000000"),
            "close": Decimal("1000000"),
        }
    )

    second, _ = builder.build_open_contexts("BTC", changed_open, open_candle.open_time)

    assert first["BTC"].atr14 == second["BTC"].atr14


def test_open_daily_candle_is_excluded_from_atr_input() -> None:
    builder, repository, open_candle = _production_daily_open_builder()

    closed = repository.get_closed_before(
        MarketSymbol.BTC,
        open_candle.timeframe,
        open_candle.open_time,
    )
    builder.build_open_contexts("BTC", open_candle, open_candle.open_time)

    assert len(closed) == 729
    assert closed[-1].open_time < open_candle.open_time
    assert all(candle.is_closed for candle in closed)


def test_repeated_btc_daily_atr_lookup_is_deterministic() -> None:
    builder, _, open_candle = _production_daily_open_builder()

    first, _ = builder.build_open_contexts("BTC", open_candle, open_candle.open_time)
    second, _ = builder.build_open_contexts("BTC", open_candle, open_candle.open_time)

    assert first["BTC"].atr14 == second["BTC"].atr14
