"""Tests for strategy evaluation service."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import StrategyEvaluationRow, TradeIntentRow
from paper_trading.enums import SignalType, TradeIntentStatus
from paper_trading.evaluation import PaperEvaluationService
from paper_trading.lifecycle import EntryGateContext, check_entry_gates
from paper_trading.mappers import evaluation_row_to_domain, intent_row_to_domain
from strategy_engine.models import StrategyParameters

from tests.backtester.conftest import make_long_entry_eval, make_no_entry_eval
from tests.paper_trading.conftest_lifecycle import make_strategy_bundle, utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def _open_gates() -> EntryGateContext:
    return EntryGateContext(
        entry_ready=True,
        market_data_ready=True,
        paused=False,
        kill_switch=False,
        open_position_count=0,
        has_symbol_position=False,
        has_nonterminal_intent=False,
    )


def _evaluation_row(symbol: str = "BTC") -> StrategyEvaluationRow:
    bundle = make_strategy_bundle(symbol)
    eval_time = bundle.evaluation_time
    daily_open_time = bundle.daily.candles[-1].open_time
    return StrategyEvaluationRow(
        evaluation_id=uuid4(),
        symbol=symbol,
        evaluation_time=eval_time,
        daily_candle_open_time=daily_open_time,
        weekly_candle_key=utc_dt(2024, 1, 8),
        monthly_candle_key=utc_dt(2024, 1, 1),
        daily_candle_key=daily_open_time,
        strategy_version="1.0",
        regime_result={"regime_long": True},
        entry_result={"signal": "LONG"},
        rejection_reasons=[],
        deterministic_input_hash="hash",
        created_at=eval_time,
    )


def _setup_repo_with_storage() -> MagicMock:
    repo = MagicMock()
    evaluations: dict[tuple[str, str, object], object] = {}
    intents: dict[tuple[object, ...], object] = {}

    def insert_eval(row: StrategyEvaluationRow):
        key = (row.strategy_version, row.symbol, row.daily_candle_open_time)
        if key in evaluations:
            return evaluations[key], False
        domain = evaluation_row_to_domain(row)
        evaluations[key] = domain
        return domain, True

    def insert_intent(row: TradeIntentRow):
        key = (row.strategy_evaluation_id, row.symbol, row.side, row.signal_type)
        if key in intents:
            return intents[key], False
        domain = intent_row_to_domain(row)
        intents[key] = domain
        return domain, True

    repo.insert_or_get_strategy_evaluation.side_effect = insert_eval
    repo.insert_or_get_trade_intent.side_effect = insert_intent
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    repo.append_audit_event.return_value = MagicMock()
    repo.get_open_positions.return_value = ()
    return repo


def test_same_evaluation_twice_one_record() -> None:
    repo = _setup_repo_with_storage()
    engine = MagicMock()
    bundle = make_strategy_bundle()
    eval_time = bundle.evaluation_time
    engine.evaluate.return_value = make_no_entry_eval("BTC", eval_time)
    service = PaperEvaluationService(repo, engine)
    params = StrategyParameters()
    r1 = service.evaluate_symbol_for_daily_close(
        symbol="BTC",
        evaluation_time=eval_time,
        bundle=bundle,
        strategy_params=params,
        config=_config(),
        entry_gates=_open_gates(),
    )
    r2 = service.evaluate_symbol_for_daily_close(
        symbol="BTC",
        evaluation_time=eval_time,
        bundle=bundle,
        strategy_params=params,
        config=_config(),
        entry_gates=_open_gates(),
    )
    assert r1.created is True
    assert r2.created is False
    assert r1.evaluation.evaluation_id == r2.evaluation.evaluation_id


def test_no_signal_evaluation_no_intent() -> None:
    repo = _setup_repo_with_storage()
    engine = MagicMock()
    bundle = make_strategy_bundle()
    eval_time = bundle.evaluation_time
    engine.evaluate.return_value = make_no_entry_eval("BTC", eval_time)
    service = PaperEvaluationService(repo, engine)
    result = service.evaluate_symbol_for_daily_close(
        symbol="BTC",
        evaluation_time=eval_time,
        bundle=bundle,
        strategy_params=StrategyParameters(),
        config=_config(),
        entry_gates=_open_gates(),
    )
    assert result.intent is None
    repo.insert_or_get_trade_intent.assert_not_called()


def test_breakout_creates_scheduled_intent() -> None:
    repo = _setup_repo_with_storage()
    engine = MagicMock()
    bundle = make_strategy_bundle()
    eval_time = bundle.evaluation_time
    engine.evaluate.return_value = make_long_entry_eval("BTC", eval_time)
    service = PaperEvaluationService(repo, engine)
    result = service.evaluate_symbol_for_daily_close(
        symbol="BTC",
        evaluation_time=eval_time,
        bundle=bundle,
        strategy_params=StrategyParameters(),
        config=_config(),
        entry_gates=_open_gates(),
    )
    assert result.intent is not None
    assert result.intent_created is True
    assert result.intent.status == TradeIntentStatus.SCHEDULED
    assert result.intent.scheduled_fill_time.date() == (bundle.daily.candles[-1].open_time.date() + timedelta(days=1))
    assert result.intent.signal_type == SignalType.BREAKOUT


def test_same_evaluation_twice_one_intent() -> None:
    repo = _setup_repo_with_storage()
    engine = MagicMock()
    bundle = make_strategy_bundle()
    eval_time = bundle.evaluation_time
    engine.evaluate.return_value = make_long_entry_eval("BTC", eval_time)
    service = PaperEvaluationService(repo, engine)
    bundle = make_strategy_bundle()
    params = StrategyParameters()
    gates = _open_gates()
    r1 = service.evaluate_symbol_for_daily_close(
        symbol="BTC",
        evaluation_time=eval_time,
        bundle=bundle,
        strategy_params=params,
        config=_config(),
        entry_gates=gates,
    )
    r2 = service.evaluate_symbol_for_daily_close(
        symbol="BTC",
        evaluation_time=eval_time,
        bundle=bundle,
        strategy_params=params,
        config=_config(),
        entry_gates=gates,
    )
    assert r1.intent_created is True
    assert r2.intent_created is False
    assert r1.intent is not None and r2.intent is not None
    assert r1.intent.intent_id == r2.intent.intent_id


def test_pause_blocks_intent() -> None:
    eval_time = utc_dt(2024, 1, 15)
    blocked = check_entry_gates(
        symbol="BTC",
        entry_gates=EntryGateContext(
            entry_ready=True,
            market_data_ready=True,
            paused=True,
            kill_switch=False,
            open_position_count=0,
            has_symbol_position=False,
            has_nonterminal_intent=False,
        ),
        strategy_eval=make_long_entry_eval("BTC", eval_time),
    )
    assert "paused" in blocked


def test_kill_switch_blocks_intent() -> None:
    eval_time = utc_dt(2024, 1, 15)
    blocked = check_entry_gates(
        symbol="BTC",
        entry_gates=EntryGateContext(
            entry_ready=True,
            market_data_ready=True,
            paused=False,
            kill_switch=True,
            open_position_count=0,
            has_symbol_position=False,
            has_nonterminal_intent=False,
        ),
        strategy_eval=make_long_entry_eval("BTC", eval_time),
    )
    assert "kill_switch" in blocked


def test_existing_position_blocks_intent() -> None:
    eval_time = utc_dt(2024, 1, 15)
    blocked = check_entry_gates(
        symbol="BTC",
        entry_gates=EntryGateContext(
            entry_ready=True,
            market_data_ready=True,
            paused=False,
            kill_switch=False,
            open_position_count=1,
            has_symbol_position=True,
            has_nonterminal_intent=False,
        ),
        strategy_eval=make_long_entry_eval("BTC", eval_time),
    )
    assert "existing_position" in blocked
