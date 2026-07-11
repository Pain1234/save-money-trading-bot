"""Integration tests for BacktestEngine — fees, funding, risk, duplicates."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backtester.data import evaluation_time_for_daily
from backtester.engine import BacktestEngine
from backtester.intent import build_client_intent_id
from backtester.models import HistoricalDataBundle
from risk_engine.models import RiskParameters
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import EntryType, ReasonCode, SignalIntent, SignalIntentKind

from tests.backtester.conftest import (
    dt,
    flat_daily_series,
    make_bundle,
    make_config,
    make_daily,
    make_insufficient_history_eval,
    make_long_entry_eval,
    make_no_entry_eval,
)


def _signal_on_day0(mock_eval, symbol: str, daily) -> None:
    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect


@patch("backtester.engine.StrategyEngine.evaluate")
def test_entry_fees_reduce_cash(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), fee_entry="0.01", fee_exit="0", slippage_bps="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.total_fees > Decimal("0")
    assert result.trades[0].fees > Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_exit_fees(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "105", "88", "89"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), fee_entry="0", fee_exit="0.01", slippage_bps="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    trade = result.trades[0]
    assert trade.fees > Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_slippage_entry(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="100", fee_entry="0", fee_exit="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    trade = result.trades[0]
    assert trade.entry_fill_price > trade.entry_reference_price
    assert trade.slippage_cost > Decimal("0")
    assert result.total_slippage > Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_slippage_exit(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "105", "88", "89"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="100", fee_entry="0", fee_exit="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    trade = result.trades[0]
    assert trade.exit_fill_price is not None
    assert trade.exit_reference_price is not None
    assert trade.exit_fill_price < trade.exit_reference_price


@patch("backtester.engine.StrategyEngine.evaluate")
def test_funding_disabled_flag(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), funding_enabled=False)
    mock_eval.return_value = make_no_entry_eval(symbol, evaluation_time_for_daily(daily[0]))
    result = BacktestEngine().run(bundle, config)
    assert result.funding_enabled is False
    assert result.total_funding == Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_funding_during_open_position(mock_eval) -> None:
    from backtester.models import FundingEvent

    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    funding = (
        FundingEvent(timestamp=dt(2024, 1, 2, 12), funding_rate=Decimal("0.001")),
    )
    bundle = make_bundle(symbol, daily=daily, funding=funding)
    config = make_config((symbol,), funding_enabled=True, slippage_bps="0", fee_entry="0", fee_exit="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.total_funding > Decimal("0")
    assert result.trades[0].funding > Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_no_funding_before_entry(mock_eval) -> None:
    from backtester.models import FundingEvent

    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
    )
    funding = (FundingEvent(timestamp=dt(2024, 1, 1, 12), funding_rate=Decimal("0.01")),)
    bundle = make_bundle(symbol, daily=daily, funding=funding)
    config = make_config((symbol,), funding_enabled=True)
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.trades[0].funding == Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_no_funding_after_exit(mock_eval) -> None:
    from backtester.models import FundingEvent

    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "105", "88", "89"),
        make_daily(symbol, dt(2024, 1, 4), "89", "90", "88", "89"),
    )
    funding = (FundingEvent(timestamp=dt(2024, 1, 4, 12), funding_rate=Decimal("0.01")),)
    bundle = make_bundle(symbol, daily=daily, funding=funding)
    config = make_config((symbol,), funding_enabled=True, slippage_bps="0", fee_entry="0", fee_exit="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 1
    assert result.trades[0].funding == Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_multiple_funding_events(mock_eval) -> None:
    from backtester.models import FundingEvent

    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    funding = (
        FundingEvent(timestamp=dt(2024, 1, 2, 8), funding_rate=Decimal("0.001")),
        FundingEvent(timestamp=dt(2024, 1, 3, 8), funding_rate=Decimal("0.002")),
    )
    bundle = make_bundle(symbol, daily=daily, funding=funding)
    config = make_config((symbol,), funding_enabled=True, slippage_bps="0", fee_entry="0", fee_exit="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.trades[0].funding > Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_future_funding_not_used(mock_eval) -> None:
    from backtester.models import FundingEvent

    symbol = "BTC"
    daily = flat_daily_series(symbol, 3)
    funding = (FundingEvent(timestamp=dt(2030, 1, 1), funding_rate=Decimal("1")),)
    bundle = make_bundle(symbol, daily=daily, funding=funding)
    config = make_config((symbol,), funding_enabled=True)
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert result.total_funding == Decimal("0")


@patch("backtester.engine.StrategyEngine.evaluate")
def test_multiple_simultaneous_signals_symbol_order(mock_eval) -> None:
    symbols = ("BTC", "ETH")
    d0, d1, d2 = dt(2024, 1, 1), dt(2024, 1, 2), dt(2024, 1, 3)
    daily_btc = (
        make_daily("BTC", d0, "100", "101", "99", "100"),
        make_daily("BTC", d1, "100", "105", "99", "104"),
        make_daily("BTC", d2, "104", "115", "103", "112"),
    )
    daily_eth = (
        make_daily("ETH", d0, "50", "51", "49", "50"),
        make_daily("ETH", d1, "50", "55", "49", "54"),
        make_daily("ETH", d2, "54", "60", "53", "58"),
    )
    bundle = HistoricalDataBundle(
        daily={"BTC": daily_btc, "ETH": daily_eth},
        weekly={"BTC": (), "ETH": ()},
        monthly={"BTC": (), "ETH": ()},
    )
    config = make_config(symbols, slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        sym = daily_s.symbol
        if eval_time == evaluation_time_for_daily(daily_btc[0]):
            return make_long_entry_eval(sym, eval_time, stop="90" if sym == "BTC" else "45", atr="2")
        return make_no_entry_eval(sym, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 2
    assert result.trades[0].symbol == "BTC"
    assert result.trades[1].symbol == "ETH"


@patch("backtester.engine.StrategyEngine.evaluate")
def test_portfolio_risk_limit_rejection(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 5)
    bundle = make_bundle(symbol, daily=daily)
    risk = RiskParameters(max_portfolio_risk_pct=Decimal("0.001"), risk_per_trade_pct=Decimal("0.01"))
    config = make_config((symbol,), risk_params=risk, slippage_bps="0", fee_entry="0", fee_exit="0")

    call_count = {"n": 0}

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.risk_rejections) >= 1 or len(result.trades) <= 1


@patch("backtester.engine.StrategyEngine.evaluate")
def test_three_open_positions_max(mock_eval) -> None:
    symbols = ("BTC", "ETH", "SOL")
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
    risk = RiskParameters(max_open_positions=3)
    config = make_config(symbols, risk_params=risk, slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily["BTC"][0]):
            return make_long_entry_eval(daily_s.symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(daily_s.symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.open_positions) == 3


@patch("backtester.engine.StrategyEngine.evaluate")
def test_risk_rejection_recorded(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
    )
    bundle = make_bundle(symbol, daily=daily)
    risk = RiskParameters(max_open_positions=0)
    config = make_config((symbol,), risk_params=risk)
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert len(result.risk_rejections) >= 1


@patch("backtester.engine.StrategyEngine.evaluate")
def test_strategy_reason_codes_preserved(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == evaluation_time_for_daily(daily[0]):
            return make_long_entry_eval(
                symbol,
                eval_time,
                stop="95",
                atr="2",
                reason_codes=(ReasonCode.RC_ENTRY_BREAKOUT_20D,),
            )
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert ReasonCode.RC_ENTRY_BREAKOUT_20D in result.trades[0].strategy_reason_codes
    assert len(result.strategy_evaluations) > 0


@patch("backtester.engine.StrategyEngine.evaluate")
def test_risk_reason_codes_preserved(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")
    _signal_on_day0(mock_eval, symbol, daily)
    result = BacktestEngine().run(bundle, config)
    assert ReasonCode.RC_RISK_APPROVED in result.trades[0].risk_reason_codes


@patch("backtester.engine.StrategyEngine.evaluate")
def test_duplicate_client_intent_id(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 4)
    bundle = make_bundle(symbol, daily=daily)
    eval_t = evaluation_time_for_daily(daily[0])
    intent_id = build_client_intent_id(symbol, STRATEGY_VERSION, eval_t, EntryType.BREAKOUT)
    config = make_config((symbol,), initial_processed=(intent_id,))

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == eval_t:
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 0
    assert intent_id in result.processed_intent_ids


@patch("backtester.engine.StrategyEngine.evaluate")
def test_resume_with_processed_intent(mock_eval) -> None:
    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
    )
    bundle = make_bundle(symbol, daily=daily)
    eval_t = evaluation_time_for_daily(daily[0])
    intent_id = build_client_intent_id(symbol, STRATEGY_VERSION, eval_t, EntryType.BREAKOUT)
    config = make_config((symbol,), initial_processed=(intent_id,), slippage_bps="0", fee_entry="0", fee_exit="0")

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        if eval_time == eval_t:
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 0


@patch("backtester.engine.StrategyEngine.evaluate")
def test_insufficient_history_no_order(mock_eval) -> None:
    symbol = "BTC"
    daily = flat_daily_series(symbol, 2)
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,))
    mock_eval.return_value = make_insufficient_history_eval(
        symbol, evaluation_time_for_daily(daily[0])
    )
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 0
    assert any(
        e.signal_intent.kind == SignalIntentKind.INSUFFICIENT_HISTORY
        for e in result.strategy_evaluations
    )


@patch("backtester.engine.StrategyEngine.evaluate")
def test_weekly_trend_break_does_not_close_position(mock_eval) -> None:
    from strategy_engine.models import TrendResult

    symbol = "BTC"
    daily = (
        make_daily(symbol, dt(2024, 1, 1), "100", "101", "99", "100"),
        make_daily(symbol, dt(2024, 1, 2), "100", "105", "99", "104"),
        make_daily(symbol, dt(2024, 1, 3), "104", "115", "103", "112"),
        make_daily(symbol, dt(2024, 1, 4), "112", "120", "111", "118"),
    )
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,), slippage_bps="0", fee_entry="0", fee_exit="0")
    day = {"n": 0}

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        day["n"] += 1
        if day["n"] == 1:
            return make_long_entry_eval(symbol, eval_time, stop="95", atr="2")
        if day["n"] >= 3:
            ev = make_no_entry_eval(symbol, eval_time)
            return ev.model_copy(
                update={
                    "weekly_trend": TrendResult(trend_confirmed=False, reason_code=ReasonCode.RC_REJECT_TREND),
                    "signal_intent": SignalIntent(kind=SignalIntentKind.NO_ENTRY),
                    "reason_codes": (ReasonCode.RC_REJECT_TREND,),
                }
            )
        return make_no_entry_eval(symbol, eval_time)

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.open_positions) == 1
    assert result.trades[0].exit_time is None


@patch("backtester.engine.StrategyEngine.evaluate")
def test_weekly_trend_break_blocks_new_entry(mock_eval) -> None:
    from strategy_engine.models import TrendResult

    symbol = "BTC"
    daily = flat_daily_series(symbol, 4)
    bundle = make_bundle(symbol, daily=daily)
    config = make_config((symbol,))

    def side_effect(daily_s, weekly_s, monthly_s, eval_time, params):
        return make_no_entry_eval(symbol, eval_time).model_copy(
            update={
                "weekly_trend": TrendResult(trend_confirmed=False, reason_code=ReasonCode.RC_REJECT_TREND),
                "reason_codes": (ReasonCode.RC_REJECT_TREND,),
            }
        )

    mock_eval.side_effect = side_effect
    result = BacktestEngine().run(bundle, config)
    assert len(result.trades) == 0
