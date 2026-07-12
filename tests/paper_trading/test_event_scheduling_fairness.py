"""Regression tests for fair market event batch scheduling (OLR-006)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.clock import FixedClock
from paper_trading.enums import SchedulerRunStatus
from paper_trading.market_event_errors import RetryableContextNotReady
from paper_trading.market_events import (
    MarketEventDetector,
    _advance_fairness_cursor,
    _select_fair_candidate_batch,
)
from paper_trading.scheduler import JobRunOutcome
from paper_trading.scheduler_context import ProductionContextBuilder

from tests.paper_trading.bridge_test_helpers import ack_result
from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.test_daily_open_event_lifecycle import (
    _build_bridge,
    _repo_with_subjob_tracking,
)


def _daily(symbol: str, open_time: datetime) -> NormalizedCandle:
    return NormalizedCandle(
        symbol=MarketSymbol(symbol),
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=daily_close(open_time),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        is_closed=False,
    )


def _open_subjob_outcome() -> JobRunOutcome:
    return JobRunOutcome(
        job_name="subjob",
        scheduled_for=utc_dt(2024, 1, 16),
        status=SchedulerRunStatus.COMPLETED,
        skipped=False,
    )


def test_fair_batch_rotates_start_index_on_overflow() -> None:
    from paper_trading.market_events import MarketEvent, MarketEventType

    events = [
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol=symbol,
            candle_open_time=utc_dt(2024, 1, 16),
            provider_received_at=utc_dt(2024, 1, 16, 1),
            observed_low=Decimal("95"),
        )
        for symbol in ("BTC", "ETH", "SOL")
    ]
    first, _, overflow = _select_fair_candidate_batch(
        events,
        max_events_per_poll=2,
        fairness_cursor=0,
    )
    second, _, _ = _select_fair_candidate_batch(
        events,
        max_events_per_poll=2,
        fairness_cursor=1,
    )
    assert overflow is True
    assert [event.symbol for event in first] == ["BTC", "ETH"]
    assert [event.symbol for event in second] == ["ETH", "SOL"]


def test_deferred_head_events_do_not_starve_later_symbol() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_time))

    def build_contexts(symbol: str, *args, **kwargs):
        if symbol in {"BTC", "ETH"}:
            raise RetryableContextNotReady(f"not ready for {symbol}")
        return ({}, {})

    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = build_contexts

    repo = _repo_with_subjob_tracking()
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(),)
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        max_events_per_poll=2,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )

    first = bridge.process_after_poll(eval_time)
    assert len(first.outcomes) == 2
    assert all(outcome.deferred for outcome in first.outcomes)
    assert context_builder.build_open_contexts.call_count == 2

    second = bridge.process_after_poll(eval_time)
    assert len(second.outcomes) == 2
    sol_outcomes = [o for o in second.outcomes if o.event.symbol == "SOL"]
    assert len(sol_outcomes) == 1
    assert sol_outcomes[0].status == SchedulerRunStatus.COMPLETED
    sol_calls = [
        call for call in context_builder.build_open_contexts.call_args_list if call.args[0] == "SOL"
    ]
    assert len(sol_calls) == 1

    ack_result(bridge, second)
    assert bridge.detector._trackers["SOL"].daily_open_ack_time == open_time  # noqa: SLF001


def test_restart_preserves_pending_deferred_events() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_time))

    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = RetryableContextNotReady("not ready")

    repo = _repo_with_subjob_tracking()
    detector = MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5)
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        max_events_per_poll=2,
        detector=detector,
    )
    bridge.process_after_poll(eval_time)

    restarted = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        max_events_per_poll=2,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )
    after_restart = restarted.process_after_poll(eval_time)
    assert len(after_restart.outcomes) == 2
    assert all(outcome.deferred for outcome in after_restart.outcomes)


def test_advance_cursor_moves_by_batch_size_without_deferred() -> None:
    from paper_trading.market_events import EventProcessOutcome, MarketEvent, MarketEventType

    event = MarketEvent(
        event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
        symbol="BTC",
        candle_open_time=utc_dt(2024, 1, 16),
        provider_received_at=utc_dt(2024, 1, 16, 1),
        observed_low=Decimal("95"),
    )
    outcome = EventProcessOutcome(
        event=event,
        job_name="me:do:BTC:20240116T000000Z",
        status=SchedulerRunStatus.COMPLETED,
        skipped=False,
    )
    assert (
        _advance_fairness_cursor(
            cursor=0,
            candidate_count=3,
            batch_size=2,
            had_overflow=True,
            outcomes=(outcome, outcome),
        )
        == 2
    )
