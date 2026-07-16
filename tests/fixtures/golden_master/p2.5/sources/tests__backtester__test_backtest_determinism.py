"""Determinism and lookahead regression tests."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine

from tests.backtester.conftest import (
    dt,
    flat_daily_series,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
)


@patch("backtester.engine.StrategyEngine.evaluate")
def test_deterministic_repeat(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 5)
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    engine = BacktestEngine()
    r1 = engine.run(bundle, config)
    r2 = engine.run(bundle, config)
    assert r1.end_capital == r2.end_capital
    assert r1.trades == r2.trades
    assert r1.processed_intent_ids == r2.processed_intent_ids


@patch("backtester.engine.StrategyEngine.evaluate")
def test_symbol_order_deterministic(mock_eval) -> None:
    from backtester.models import HistoricalDataBundle

    symbols = ("SOL", "BTC", "ETH")
    d0, d1, d2 = dt(2024, 1, 1), dt(2024, 1, 2), dt(2024, 1, 3)
    daily = {
        s: (
            make_daily(s, d0, "100", "101", "99", "100"),
            make_daily(s, d1, "100", "105", "99", "104"),
            make_daily(s, d2, "104", "115", "103", "112"),
        )
        for s in symbols
    }
    bundle = HistoricalDataBundle(
        daily=daily,
        weekly={s: () for s in symbols},
        monthly={s: () for s in symbols},
    )
    config = make_config(symbols, slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily["SOL"][0]):
            return make_long_entry_eval(daily_s.symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(daily_s.symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    filled = [p.symbol for p in result.open_positions]
    assert filled == ["SOL", "BTC", "ETH"]


@patch("backtester.engine.StrategyEngine.evaluate")
def test_missing_candle_skipped(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 3), "100", "105", "99", "104"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,))
    mock_eval.return_value = make_no_entry_eval(symbol, evaluation_time_for_daily(daily[0]))
    result = BacktestEngine().run(bundle, config)
    assert result.data_start == dt(2024, 1, 1)


def test_nan_position_filtered() -> None:
    from backtester.models import SimulatedPosition
    from backtester.portfolio import to_position_states

    pos = SimulatedPosition(
        symbol="BTC",
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_time=dt(2024, 1, 1),
        initial_stop=Decimal("90"),
        trail_stop=Decimal("90"),
        effective_stop=Decimal("90"),
        highest_close=Decimal("100"),
        entry_atr14=Decimal("2"),
        client_intent_id="x",
        margin_reserved=Decimal("50"),
    )
    states = to_position_states((pos,), {"BTC": Decimal("100")})
    assert len(states) == 1
    bad = pos.model_copy(update={"quantity": Decimal("-1")})
    assert to_position_states((bad,), {"BTC": Decimal("100")}) == ()
