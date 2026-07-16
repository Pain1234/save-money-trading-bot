"""Offline backtester vs strategy-engine signal parity (R-004 / #48).

Uses identical HistoricalDataBundle candles and StrategyParameters.
Does not require Postgres or live network.
"""

from __future__ import annotations

from backtester.data import (
    build_candle_series,
    evaluation_time_for_daily,
    slice_closed_candles,
)
from backtester.engine import BacktestEngine
from strategy_engine.engine import StrategyEngine
from strategy_engine.models import SignalIntentKind, Timeframe

from tests.paper_trading.e2e.helpers import (
    backtest_config_for_symbols,
    build_breakout_historical_bundle,
)


def _signal_signature(kind: SignalIntentKind, entry_type: object | None) -> tuple[str, str]:
    return (kind.value, str(entry_type) if entry_type is not None else "")


def test_backtester_strategy_engine_signal_parity_breakout() -> None:
    """Backtester evaluations must match StrategyEngine on the same closed candles."""
    symbol = "BTC"
    hist = build_breakout_historical_bundle(symbol, include_exit_candle=True)
    config = backtest_config_for_symbols((symbol,))
    bt = BacktestEngine().run(hist, config)

    engine = StrategyEngine()
    params = config.strategy_params
    daily = hist.daily[symbol]
    weekly = hist.weekly[symbol]
    monthly = hist.monthly[symbol]

    # Compare every LONG_ENTRY / NO_ENTRY decision at each daily close event.
    bt_by_time = {
        e.evaluation_time: e
        for e in bt.strategy_evaluations
        if e.symbol == symbol
    }
    assert bt_by_time, "backtester produced no strategy evaluations"

    matched = 0
    for candle in daily:
        if not candle.is_closed:
            continue
        eval_time = evaluation_time_for_daily(candle)
        # Only evaluate when we have the same as-of view the backtester used.
        if eval_time not in bt_by_time:
            continue
        daily_series = build_candle_series(symbol, Timeframe.DAILY, daily, eval_time)
        weekly_series = build_candle_series(symbol, Timeframe.WEEKLY, weekly, eval_time)
        monthly_series = build_candle_series(symbol, Timeframe.MONTHLY, monthly, eval_time)
        # Warm-up guard: need enough closed dailies
        closed = slice_closed_candles(daily, eval_time)
        if len(closed) < 5:
            continue
        independent = engine.evaluate(
            daily_series,
            weekly_series,
            monthly_series,
            eval_time,
            parameters=params,
        )
        bt_eval = bt_by_time[eval_time]
        assert _signal_signature(
            bt_eval.signal_intent.kind,
            bt_eval.selected_entry_type,
        ) == _signal_signature(
            independent.signal_intent.kind,
            independent.selected_entry_type,
        )
        assert bt_eval.reason_codes == independent.reason_codes
        matched += 1

    assert matched >= 1
    # Breakout fixture should produce at least one long entry in the backtester.
    entries = [
        e
        for e in bt.strategy_evaluations
        if e.signal_intent.kind == SignalIntentKind.LONG_ENTRY
    ]
    assert len(entries) >= 1


def test_identical_candle_and_config_determinism() -> None:
    """Same bundle + config → identical evaluation sequence (golden-master seed)."""
    symbol = "BTC"
    hist = build_breakout_historical_bundle(symbol)
    config = backtest_config_for_symbols((symbol,))
    a = BacktestEngine().run(hist, config)
    b = BacktestEngine().run(hist, config)
    sig_a = [
        (e.evaluation_time, e.signal_intent.kind, e.selected_entry_type, e.reason_codes)
        for e in a.strategy_evaluations
    ]
    sig_b = [
        (e.evaluation_time, e.signal_intent.kind, e.selected_entry_type, e.reason_codes)
        for e in b.strategy_evaluations
    ]
    assert sig_a == sig_b
    assert len(a.trades) == len(b.trades)
