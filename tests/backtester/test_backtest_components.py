"""Unit tests for backtester components."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from backtester.data import (
    build_candle_series,
    evaluation_time_for_daily,
    slice_closed_candles,
    validate_chronological,
)
from backtester.engine import BacktestEngine
from backtester.execution import (
    apply_entry_slippage,
    apply_exit_slippage,
    compute_fee,
    compute_funding_payment,
    compute_slippage_cost,
)
from backtester.intent import build_client_intent_id
from backtester.models import ExitReason, SlippageModel
from backtester.portfolio import to_position_states
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import EntryType, Timeframe

from tests.backtester.conftest import (
    DEFAULT_CONSTRAINTS,
    dt,
    flat_daily_series,
    make_bundle,
    make_config,
    make_daily,
    make_long_entry_eval,
    make_no_entry_eval,
    make_weekly,
)


def test_entry_slippage_worsens_price() -> None:
    model = SlippageModel(slippage_bps=Decimal("10"))
    ref = Decimal("100")
    fill = apply_entry_slippage(ref, model)
    assert fill == Decimal("100.1")
    assert fill > ref


def test_exit_slippage_worsens_price() -> None:
    model = SlippageModel(slippage_bps=Decimal("10"))
    ref = Decimal("100")
    fill = apply_exit_slippage(ref, model)
    assert fill == Decimal("99.9")
    assert fill < ref


def test_entry_fee_on_notional() -> None:
    notional = Decimal("10000")
    fee = compute_fee(notional, Decimal("0.001"))
    assert fee == Decimal("10")


def test_exit_fee_on_notional() -> None:
    notional = Decimal("5000")
    fee = compute_fee(notional, Decimal("0.0005"))
    assert fee == Decimal("2.5")


def test_slippage_cost() -> None:
    cost = compute_slippage_cost(Decimal("100"), Decimal("100.05"), Decimal("2"))
    assert cost == Decimal("0.10")


def test_funding_payment_positive_rate() -> None:
    payment = compute_funding_payment(Decimal("10000"), Decimal("0.0001"))
    assert payment == Decimal("1")


def test_deterministic_client_intent_id() -> None:
    t = dt(2024, 6, 1, 23)
    a = build_client_intent_id("BTC", STRATEGY_VERSION, t, EntryType.BREAKOUT)
    b = build_client_intent_id("BTC", STRATEGY_VERSION, t, EntryType.BREAKOUT)
    assert a == b
    assert "BTC" in a and "BREAKOUT" in a


def test_slice_closed_candles_no_lookahead() -> None:
    candles = flat_daily_series("BTC", 5)
    as_of = candles[2].close_time
    sliced = slice_closed_candles(candles, as_of)
    assert len(sliced) == 3
    assert all(c.close_time <= as_of for c in sliced)


def test_build_candle_series_excludes_future() -> None:
    candles = flat_daily_series("BTC", 10)
    as_of = candles[4].close_time
    series = build_candle_series("BTC", Timeframe.DAILY, candles, as_of)
    assert series.length == 5


def test_open_weekly_candle_excluded() -> None:
    candles = (
        make_weekly("BTC", dt(2024, 1, 1), "100", "105", "95", "100", is_closed=False),
        make_weekly("BTC", dt(2024, 1, 8), "100", "105", "95", "100", is_closed=True),
    )
    as_of = dt(2024, 1, 15)
    series = build_candle_series("BTC", Timeframe.WEEKLY, candles, as_of)
    assert series.length == 1
    assert series.candles[0].open_time == dt(2024, 1, 8)


def test_future_monthly_candle_excluded() -> None:
    from tests.backtester.conftest import make_monthly

    candles = (
        make_monthly("BTC", 2024, 1, "100", is_closed=True),
        make_monthly("BTC", 2024, 2, "100", is_closed=True),
    )
    as_of = make_monthly("BTC", 2024, 1).close_time
    series = build_candle_series("BTC", Timeframe.MONTHLY, candles, as_of)
    assert series.length == 1


def test_validate_duplicate_candle() -> None:
    c = make_daily("BTC", dt(2024, 1, 1), "100", "101", "99", "100")
    warnings = validate_chronological((c, c))
    assert any("duplicate" in w for w in warnings)


def test_validate_unsorted_candles() -> None:
    c1 = make_daily("BTC", dt(2024, 1, 2), "100", "101", "99", "100")
    c2 = make_daily("BTC", dt(2024, 1, 1), "100", "101", "99", "100")
    warnings = validate_chronological((c1, c2))
    assert any("unsorted" in w for w in warnings)


def test_validate_open_candle_warning() -> None:
    c = make_daily("BTC", dt(2024, 1, 1), "100", "101", "99", "100", is_closed=False)
    warnings = validate_chronological((c,))
    assert any("open candle" in w for w in warnings)


def test_to_position_states_skips_invalid() -> None:
    from backtester.models import SimulatedPosition

    pos = SimulatedPosition(
        symbol="BTC",
        quantity=Decimal("0"),
        entry_price=Decimal("100"),
        entry_time=dt(2024, 1, 1),
        initial_stop=Decimal("90"),
        trail_stop=Decimal("90"),
        effective_stop=Decimal("90"),
        highest_close=Decimal("100"),
        entry_atr14=Decimal("2"),
        client_intent_id="x",
        margin_reserved=Decimal("0"),
    )
    states = to_position_states((pos,), {"BTC": Decimal("100")})
    assert states == ()


def test_evaluation_time_buffer() -> None:
    c = make_daily("BTC", dt(2024, 1, 1), "100", "101", "99", "100")
    eval_t = evaluation_time_for_daily(c)
    assert eval_t == c.close_time + timedelta(seconds=5)


@patch("backtester.engine.StrategyEngine.evaluate")
def test_entry_at_next_open_not_signal_close(mock_eval) -> None:
    symbol = "BTC"
    d0 = dt(2024, 1, 1)
    d1 = dt(2024, 1, 2)
    daily = (
        make_daily(symbol, d0, "98", "102", "97", "100"),
        make_daily(symbol, d1, "101", "110", "100", "108"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(
                symbol, eval_time, entry_price="100", stop="95", atr="2"
            )
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == d1
    assert trade.entry_reference_price == Decimal("101")
    assert trade.entry_reference_price != Decimal("100")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_no_execution_at_signal_close(mock_eval) -> None:
    symbol = "BTC"
    d0 = dt(2024, 1, 1)
    daily = (make_daily(symbol, d0, "100", "105", "99", "104"),)
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    mock_eval.return_value = make_long_entry_eval(
        symbol,
        evaluation_time_for_daily(daily[0]),
        entry_price="104",
        stop="98",
        atr="2",
    )
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 0


@patch("backtester.engine.StrategyEngine.evaluate")
def test_simple_winning_trade(mock_eval) -> None:
    symbol = "BTC"
    days = [dt(2024, 1, 1) + timedelta(days=i) for i in range(5)]
    daily = (
        make_daily(symbol, days[0], "100", "101", "99", "100"),
        make_daily(symbol, days[1], "100", "105", "99", "104"),
        make_daily(symbol, days[2], "104", "115", "103", "112"),
        make_daily(symbol, days[3], "112", "120", "111", "118"),
        make_daily(symbol, days[4], "118", "125", "117", "122"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 1
    assert result.trades[0].exit_time is None
    assert result.end_capital > config.initial_cash


@patch("backtester.engine.StrategyEngine.evaluate")
def test_simple_losing_trade_stop(mock_eval) -> None:
    symbol = "BTC"
    d0, d1, d2 = dt(2024, 1, 1), dt(2024, 1, 2), dt(2024, 1, 3)
    daily = (
        make_daily(symbol, d0, "100", "101", "99", "100"),
        make_daily(symbol, d1, "100", "105", "99", "104"),
        make_daily(symbol, d2, "104", "105", "88", "89"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason in (ExitReason.STOP_INITIAL, ExitReason.STOP_TRAILING)
    assert trade.net_pnl is not None and trade.net_pnl < 0


@patch("backtester.engine.StrategyEngine.evaluate")
def test_stop_without_gap(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "105", "93", "94"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    trade = result.trades[0]
    assert trade.exit_reason != ExitReason.STOP_GAP
    assert trade.exit_reference_price == Decimal("98")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_stop_with_gap(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "90", "92", "85", "86"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.STOP_GAP
    assert trade.exit_reference_price == Decimal("90")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_trailing_stop_rises(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
        make_daily(symbol, dt(2024, 1, 4), "112", "120", "111", "118"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    pos = result.open_positions[0]
    assert pos.trail_stop >= pos.initial_stop


@patch("backtester.engine.StrategyEngine.evaluate")
def test_trailing_stop_never_decreases(mock_eval) -> None:
    from strategy_engine.models import StrategyParameters
    from strategy_engine.stops import initialize_trailing_stop, update_trailing_stop

    params = StrategyParameters()
    tick = DEFAULT_CONSTRAINTS.price_tick_size
    state = initialize_trailing_stop(Decimal("100"), Decimal("2"), Decimal("95"), params, tick)
    prev_trail = state.trail_stop
    for close in [Decimal("110"), Decimal("105"), Decimal("108")]:
        state = update_trailing_stop(state, close, Decimal("2"), params, tick)
        assert state.trail_stop >= prev_trail
        prev_trail = state.trail_stop


@patch("backtester.engine.StrategyEngine.evaluate")
def test_entry_and_stop_same_candle_conservative(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "101", "88", "89"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    trade = result.trades[0]
    assert trade.exit_time == dt(2024, 1, 2)
    assert trade.net_pnl is not None and trade.net_pnl < 0
