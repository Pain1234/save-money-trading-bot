"""Regression tests for persistent group fairness and open-batch ordering."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.clock import FixedClock
from paper_trading.enums import SchedulerRunStatus
from paper_trading.event_fairness import (
    advance_group_rotation_cursor,
    group_events,
    market_event_group_key,
    ordered_group_keys,
)
from paper_trading.market_event_errors import RetryableContextNotReady
from paper_trading.market_events import (
    MarketEvent,
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
)
from paper_trading.scheduler import JobRunOutcome
from paper_trading.scheduler_context import ProductionContextBuilder

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.test_daily_open_event_lifecycle import (
    _build_bridge as _build_unit_bridge,
)
from tests.paper_trading.test_daily_open_event_lifecycle import (
    _repo_with_subjob_tracking,
)

pytestmark_postgres = [requires_postgres, pytest.mark.postgres]


def _daily(symbol: str, open_time: datetime, *, is_closed: bool = False) -> NormalizedCandle:
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
        is_closed=is_closed,
    )


def _open_subjob_outcome(scheduled_for: datetime) -> JobRunOutcome:
    return JobRunOutcome(
        job_name="subjob",
        scheduled_for=scheduled_for,
        status=SchedulerRunStatus.COMPLETED,
        skipped=False,
    )


def _open_events(open_time: datetime) -> list[MarketEvent]:
    return [
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol=symbol,
            candle_open_time=open_time,
            provider_received_at=open_time + timedelta(hours=1),
            observed_low=Decimal("95"),
        )
        for symbol in ("BTC", "ETH", "SOL")
    ]


def test_group_key_preserves_symbol_order_within_open_batch() -> None:
    open_time = utc_dt(2024, 1, 16)
    grouped = group_events(_open_events(open_time))
    keys = ordered_group_keys(grouped)
    assert len(keys) == 1
    assert [event.symbol for event in grouped[keys[0]]] == ["BTC", "ETH", "SOL"]


def test_group_fairness_rotates_between_independent_groups() -> None:
    events = _open_events(utc_dt(2024, 1, 16)) + _open_events(utc_dt(2024, 1, 17))
    grouped = group_events(events)
    keys = ordered_group_keys(grouped)
    assert len(keys) == 2
    assert (
        advance_group_rotation_cursor(
            cursor=0,
            eligible_group_count=2,
            groups_rotated=1,
            had_deferred=True,
        )
        == 1
    )


def test_shared_open_batch_defers_do_not_reorder_symbols() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_time))

    context_builder = MagicMock(spec=ProductionContextBuilder)

    def build_contexts(symbol: str, *args, **kwargs):
        if symbol == "BTC":
            raise RetryableContextNotReady("btc not ready")
        return ({}, {})

    context_builder.build_open_contexts.side_effect = build_contexts

    repo = _repo_with_subjob_tracking()
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(open_time),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(open_time),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(open_time),)
    bridge = _build_unit_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        max_events_per_poll=3,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )

    result = bridge.process_after_poll(eval_time)
    assert len(result.outcomes) == 1
    assert result.outcomes[0].event.symbol == "BTC"
    assert result.outcomes[0].deferred is True
    assert context_builder.build_open_contexts.call_count == 1
    assert all(call.args[0] != "SOL" for call in context_builder.build_open_contexts.call_args_list)


def test_independent_group_processes_while_older_open_batch_deferred() -> None:
    open_old = utc_dt(2024, 1, 16)
    open_new = utc_dt(2024, 1, 17)
    eval_time = utc_dt(2024, 1, 17, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_old))
        candle_repo.upsert(_daily(symbol, open_new, is_closed=False))

    context_builder = MagicMock(spec=ProductionContextBuilder)

    def build_contexts(symbol: str, candle, *args, **kwargs):
        if candle.open_time == open_old:
            raise RetryableContextNotReady(f"old open not ready for {symbol}")
        return ({}, {})

    context_builder.build_open_contexts.side_effect = build_contexts

    repo = _repo_with_subjob_tracking()
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    scheduler.run_daily_open_fill.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    scheduler.run_daily_open_snapshot.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    bridge = _build_unit_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        max_events_per_poll=2,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )

    result = bridge.process_after_poll(eval_time)
    assert any(outcome.event.candle_open_time == open_new for outcome in result.outcomes)
    assert any(outcome.status == SchedulerRunStatus.COMPLETED for outcome in result.outcomes)


def test_restart_fairness_cursor_survives_new_bridge_instance() -> None:
    open_old = utc_dt(2024, 1, 16)
    open_new = utc_dt(2024, 1, 17)
    eval_time = utc_dt(2024, 1, 17, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_old))
        candle_repo.upsert(_daily(symbol, open_new, is_closed=False))

    context_builder = MagicMock(spec=ProductionContextBuilder)

    def build_contexts(symbol: str, candle, *args, **kwargs):
        if candle.open_time == open_old:
            raise RetryableContextNotReady(f"old open not ready for {symbol}")
        return ({}, {})

    context_builder.build_open_contexts.side_effect = build_contexts

    repo = _repo_with_subjob_tracking()
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    scheduler.run_daily_open_fill.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    scheduler.run_daily_open_snapshot.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )

    first_bridge = _build_unit_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        max_events_per_poll=2,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )
    first_bridge.process_after_poll(eval_time)

    restarted = _build_unit_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        max_events_per_poll=2,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )
    second = restarted.process_after_poll(eval_time)
    assert any(
        outcome.event.candle_open_time == open_new and outcome.status == SchedulerRunStatus.COMPLETED
        for outcome in second.outcomes
    )


@pytest.mark.asyncio
@pytest.mark.postgres
@requires_postgres
async def test_postgres_restart_cursor_fairness_with_new_bridge(
    migrated_engine,
    postgres_commit_session,
    clean_production_db,
    postgres_runtime_writable,
) -> None:
    """Fairness cursor and deferred groups survive a new bridge after DB commit."""
    from unittest.mock import MagicMock

    from paper_trading.db.orm import MarketEventGroupStateRow
    from paper_trading.repository import PaperTradingRepository

    open_old = utc_dt(2024, 1, 16)
    open_new = utc_dt(2024, 1, 17)
    eval_time = utc_dt(2024, 1, 17, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_old))
        candle_repo.upsert(_daily(symbol, open_new, is_closed=False))

    context_builder = MagicMock(spec=ProductionContextBuilder)

    def build_contexts(symbol: str, candle, *args, **kwargs):
        if candle.open_time == open_old:
            raise RetryableContextNotReady(f"old open not ready for {symbol}")
        return ({}, {})

    context_builder.build_open_contexts.side_effect = build_contexts

    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    scheduler.run_daily_open_fill.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )
    scheduler.run_daily_open_snapshot.side_effect = (
        lambda scheduled_for, **kwargs: (_open_subjob_outcome(scheduled_for),)
    )

    repo = PaperTradingRepository(postgres_commit_session)
    old_group_key = market_event_group_key(
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol="BTC",
            candle_open_time=open_old,
            provider_received_at=open_old,
        )
    )
    postgres_commit_session.add(
        MarketEventGroupStateRow(
            group_key=old_group_key,
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE.value,
            group_time=open_old,
            next_attempt_at=eval_time + timedelta(hours=1),
            defer_count=3,
            updated_at=eval_time,
        )
    )
    repo.set_fairness_group_rotation_cursor(cursor=0, updated_at=eval_time)
    postgres_commit_session.commit()

    advisory_lock = MagicMock()
    advisory_lock.held = True
    bridge_kwargs = dict(
        candle_repository=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        config=MagicMock(
            symbols=("BTC", "ETH", "SOL"),
            evaluation_delay_seconds=5,
            fill_delay_seconds=0,
        ),
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        max_events_per_poll=2,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )

    first_bridge = MarketEventBridge(repository=repo, **bridge_kwargs)
    first_bridge.process_after_poll(eval_time)
    postgres_commit_session.commit()
    cursor_after_first = repo.get_fairness_group_rotation_cursor()

    restarted_repo = PaperTradingRepository(postgres_commit_session)
    second_bridge = MarketEventBridge(repository=restarted_repo, **bridge_kwargs)
    second = second_bridge.process_after_poll(eval_time)
    postgres_commit_session.commit()

    assert cursor_after_first != 0 or any(
        outcome.event.candle_open_time == open_new for outcome in second.outcomes
    )
    assert any(
        outcome.event.candle_open_time == open_new and outcome.status == SchedulerRunStatus.COMPLETED
        for outcome in second.outcomes
    )
    assert restarted_repo.get_fairness_group_rotation_cursor() >= 0


def test_open_batch_processes_btc_eth_sol_after_btc_ready() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    for symbol in ("BTC", "ETH", "SOL"):
        candle_repo.upsert(_daily(symbol, open_time))

    context_builder = MagicMock(spec=ProductionContextBuilder)
    attempts = {"BTC": 0}

    def build_contexts(symbol: str, *args, **kwargs):
        if symbol == "BTC":
            attempts["BTC"] += 1
            if attempts["BTC"] == 1:
                raise RetryableContextNotReady("btc not ready")
        return ({}, {})

    context_builder.build_open_contexts.side_effect = build_contexts

    repo = _repo_with_subjob_tracking()
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(open_time),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(open_time),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(open_time),)
    bridge = _build_unit_bridge(
        repo=repo,
        candle_repo=candle_repo,
        clock=FixedClock(eval_time),
        context_builder=context_builder,
        scheduler=scheduler,
        max_events_per_poll=3,
        detector=MarketEventDetector(symbols=("BTC", "ETH", "SOL"), evaluation_delay_seconds=5),
    )

    first = bridge.process_after_poll(eval_time)
    assert len(first.outcomes) == 1
    assert first.outcomes[0].event.symbol == "BTC"

    second = bridge.process_after_poll(eval_time + timedelta(seconds=2))
    symbols = [outcome.event.symbol for outcome in second.outcomes]
    assert symbols == ["BTC", "ETH", "SOL"]
