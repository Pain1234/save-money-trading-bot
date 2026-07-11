"""Regression tests for gap vs intraday stop data contract."""

from __future__ import annotations

from decimal import Decimal

from backtester.models import ExitReason
from backtester.paper_lifecycle import (
    compute_gap_stop_at_open,
    compute_intraday_stop,
    compute_stop_trigger,
)

from tests.backtester.conftest import make_daily
from tests.paper_trading.conftest_execution import utc_dt


def test_gap_stop_uses_open_only() -> None:
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "47000", "50000", "46000", "48000")
    trigger = compute_gap_stop_at_open(candle, effective_stop=Decimal("48000"))
    assert trigger is not None
    assert trigger.exit_reason == ExitReason.STOP_GAP
    assert trigger.exit_reference == Decimal("47000")


def test_open_above_stop_no_gap_exit() -> None:
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "50000", "51000", "49000", "50500")
    assert compute_gap_stop_at_open(candle, effective_stop=Decimal("48000")) is None


def test_intraday_stop_uses_low_not_future_daily_low_at_open() -> None:
    open_candle = make_daily("BTC", utc_dt(2024, 1, 17), "50000", "50100", "49900", "50050")
    assert compute_gap_stop_at_open(open_candle, effective_stop=Decimal("48000")) is None
    assert (
        compute_intraday_stop(
            open_candle,
            effective_stop=Decimal("48000"),
            initial_stop=Decimal("48000"),
            trail_stop=Decimal("48000"),
        )
        is None
    )


def test_intraday_stop_triggers_when_low_hits_stop() -> None:
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "50000", "50100", "47900", "48000")
    trigger = compute_intraday_stop(
        candle,
        effective_stop=Decimal("49000"),
        initial_stop=Decimal("49000"),
        trail_stop=Decimal("48000"),
    )
    assert trigger is not None
    assert trigger.exit_reason == ExitReason.STOP_INITIAL


def test_full_daily_candle_combines_gap_and_intraday() -> None:
    candle = make_daily("BTC", utc_dt(2024, 1, 17), "50000", "50100", "47900", "48000")
    trigger = compute_stop_trigger(
        candle,
        effective_stop=Decimal("48000"),
        initial_stop=Decimal("48000"),
        trail_stop=Decimal("48000"),
    )
    assert trigger is not None
