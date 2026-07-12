"""Regression tests for market-data event bridge."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.market_events import (
    MarketEventBridge,
    MarketEventDetector,
    MarketEventType,
    market_event_job_name,
)
from paper_trading.scheduler_context import ProductionContextBuilder

from tests.paper_trading.conftest_execution import utc_dt


def _daily(
    symbol: str,
    open_time: datetime,
    *,
    low: str = "95",
    close: str = "100",
    is_closed: bool = True,
) -> NormalizedCandle:
    return NormalizedCandle(
        symbol=MarketSymbol(symbol),
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=daily_close(open_time),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


def test_daily_open_event_key_is_deterministic() -> None:
    from paper_trading.market_events import MarketEvent

    event = MarketEvent(
        event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
        symbol="BTC",
        candle_open_time=utc_dt(2024, 1, 16),
        provider_received_at=utc_dt(2024, 1, 16, 1),
    )
    assert market_event_job_name(event) == "me:do:BTC:20240116T000000Z"


def test_detector_daily_open_only_once() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",))
    candle = _daily("BTC", utc_dt(2024, 1, 16), is_closed=False)
    repo.upsert(candle)
    first = detector.detect(repo, utc_dt(2024, 1, 16, 1))
    second = detector.detect(repo, utc_dt(2024, 1, 16, 2))
    assert len([e for e in first if e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE]) == 1
    assert len([e for e in second if e.event_type == MarketEventType.DAILY_OPEN_AVAILABLE]) == 0


def test_live_update_does_not_emit_trailing_event() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",))
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    repo.upsert_live(_daily("BTC", open_time, low="95", is_closed=False), eval_time)
    detector.detect(repo, eval_time)
    repo.upsert_live(_daily("BTC", open_time, low="90", is_closed=False), eval_time)
    events = detector.detect(repo, utc_dt(2024, 1, 16, 2))
    assert any(e.event_type == MarketEventType.DAILY_LIVE_UPDATE for e in events)
    assert not any(e.event_type == MarketEventType.DAILY_CLOSED for e in events)


def test_closed_candle_emits_daily_closed_once() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5)
    open_time = utc_dt(2024, 1, 15)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    due = daily_close(open_time) + timedelta(seconds=5)
    first = detector.detect(repo, due)
    second = detector.detect(repo, due + timedelta(hours=1))
    assert len([e for e in first if e.event_type == MarketEventType.DAILY_CLOSED]) == 1
    assert len([e for e in second if e.event_type == MarketEventType.DAILY_CLOSED]) == 0


def test_daily_closed_not_emitted_before_evaluation_due() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5)
    open_time = utc_dt(2024, 1, 15)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    due = daily_close(open_time) + timedelta(seconds=5)
    before_due = due - timedelta(microseconds=1)
    events = detector.detect(repo, before_due)
    assert not any(e.event_type == MarketEventType.DAILY_CLOSED for e in events)
    assert detector._trackers["BTC"].daily_closed_open_time is None  # noqa: SLF001


def test_daily_closed_emitted_at_due_on_same_detector_instance() -> None:
    repo = InMemoryCandleRepository()
    detector = MarketEventDetector(symbols=("BTC",), evaluation_delay_seconds=5)
    open_time = utc_dt(2024, 1, 15)
    repo.upsert(_daily("BTC", open_time, is_closed=True))
    due = daily_close(open_time) + timedelta(seconds=5)
    before = detector.detect(repo, due - timedelta(microseconds=1))
    assert not any(e.event_type == MarketEventType.DAILY_CLOSED for e in before)
    at_due = detector.detect(repo, due)
    assert len([e for e in at_due if e.event_type == MarketEventType.DAILY_CLOSED]) == 1


def test_queue_overflow_is_fail_closed() -> None:
    from paper_trading.market_events import MarketEvent

    repo = MagicMock()
    repo.get_scheduler_run.return_value = None
    candle_repo = InMemoryCandleRepository()
    scheduler = MagicMock()
    context_builder = MagicMock(spec=ProductionContextBuilder)
    advisory_lock = MagicMock()
    advisory_lock.held = True

    detector = MagicMock()
    detector.detect.return_value = (
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol="BTC",
            candle_open_time=utc_dt(2024, 1, 16),
            provider_received_at=utc_dt(2024, 1, 16, 1),
        ),
        MarketEvent(
            event_type=MarketEventType.DAILY_OPEN_AVAILABLE,
            symbol="BTC",
            candle_open_time=utc_dt(2024, 1, 17),
            provider_received_at=utc_dt(2024, 1, 17, 1),
        ),
    )

    bridge = MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=scheduler,
        context_builder=context_builder,
        config=MagicMock(symbols=("BTC",), evaluation_delay_seconds=5),
        clock=MagicMock(now=lambda: utc_dt(2024, 1, 16)),
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=detector,
        max_events_per_poll=1,
    )
    outcomes = bridge.process_after_poll(utc_dt(2024, 1, 16, 1))
    assert bridge.queue_overflow is True
    assert outcomes[0].error == "event_queue_overflow"
