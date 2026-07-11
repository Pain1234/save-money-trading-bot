# ruff: noqa: E402
"""Deterministic multi-phase candle scenarios for paper trading soak tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[3] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from backtester.models import HistoricalDataBundle

from tests.strategy_engine.conftest import (
    build_rising_monthly_series,
    build_rising_weekly_series,
    dt,
    make_daily_candle,
)

SYMBOLS = ("BTC", "ETH", "SOL")


@dataclass(frozen=True)
class ScenarioEvent:
    day: int
    open_: str
    high: str
    low: str
    close: str
    volume: str = "2000"


def _flat(symbol: str, open_time, price: str = "100", vol: str = "1000"):
    p = Decimal(price)
    return make_daily_candle(symbol, open_time, price, str(p + 2), str(p - 1), price, vol=vol)


def _events_for_seed(seed: int) -> dict[str, dict[int, ScenarioEvent]]:
    shift = (seed - 1) * 5
    return {
        "BTC": {
            29: ScenarioEvent(29, "100", "130", "99", "125"),
            30: ScenarioEvent(30, "125", "128", "120", "127"),
            31: ScenarioEvent(31, "127", "131", "122", "130"),
            32: ScenarioEvent(32, "130", "135", "125", "133"),
            33: ScenarioEvent(33, "133", "138", "128", "136"),
            34: ScenarioEvent(34, "136", "141", "131", "139"),
            35: ScenarioEvent(35, "112", "113", "85", "88"),
            44: ScenarioEvent(44, "88", "130", "87", "125", "50"),
            49 + shift: ScenarioEvent(49 + shift, "100", "130", "99", "125"),
            50 + shift: ScenarioEvent(50 + shift, "125", "128", "120", "127"),
            51 + shift: ScenarioEvent(51 + shift, "127", "131", "122", "130"),
            52 + shift: ScenarioEvent(52 + shift, "130", "135", "125", "133"),
            53 + shift: ScenarioEvent(53 + shift, "133", "138", "128", "136"),
            54 + shift: ScenarioEvent(54 + shift, "136", "141", "131", "139"),
            56 + shift: ScenarioEvent(56 + shift, "118", "119", "105", "116"),
            145 + shift: ScenarioEvent(145 + shift, "100", "130", "99", "125"),
            146 + shift: ScenarioEvent(146 + shift, "125", "128", "120", "127"),
        },
        "ETH": {
            29: ScenarioEvent(29, "100", "130", "99", "125"),
            30: ScenarioEvent(30, "125", "128", "120", "127"),
            31: ScenarioEvent(31, "127", "131", "122", "130"),
            32: ScenarioEvent(32, "130", "135", "125", "133"),
            33: ScenarioEvent(33, "133", "138", "128", "136"),
            34: ScenarioEvent(34, "136", "141", "131", "139"),
            38: ScenarioEvent(38, "118", "119", "105", "116"),
            69 + shift: ScenarioEvent(69 + shift, "100", "130", "100", "125"),
            70 + shift: ScenarioEvent(70 + shift, "125", "128", "120", "127"),
            71 + shift: ScenarioEvent(71 + shift, "127", "131", "122", "130"),
            72 + shift: ScenarioEvent(72 + shift, "130", "135", "125", "133"),
            73 + shift: ScenarioEvent(73 + shift, "133", "138", "128", "136"),
            75 + shift: ScenarioEvent(75 + shift, "112", "113", "88", "90"),
        },
        "SOL": {
            29: ScenarioEvent(29, "100", "130", "99", "125"),
            30: ScenarioEvent(30, "125", "128", "120", "127"),
            31: ScenarioEvent(31, "127", "131", "122", "130"),
            32: ScenarioEvent(32, "130", "135", "125", "133"),
            33: ScenarioEvent(33, "133", "138", "128", "136"),
            40: ScenarioEvent(40, "112", "113", "88", "90"),
            80 + shift: ScenarioEvent(80 + shift, "100", "102", "100", "101", "1500"),
            81 + shift: ScenarioEvent(81 + shift, "101", "130", "100", "125"),
            82 + shift: ScenarioEvent(82 + shift, "125", "128", "120", "127"),
            83 + shift: ScenarioEvent(83 + shift, "127", "131", "122", "130"),
            84 + shift: ScenarioEvent(84 + shift, "130", "135", "125", "133"),
            86 + shift: ScenarioEvent(86 + shift, "110", "111", "88", "90"),
            120 + shift: ScenarioEvent(120 + shift, "100", "130", "99", "125"),
        },
    }


def generate_soak_bundle(*, days: int, seed: int) -> HistoricalDataBundle:
    events = _events_for_seed(seed)
    daily: dict[str, tuple] = {}
    start = dt(2024, 1, 1)
    for symbol in SYMBOLS:
        candles = []
        sym_events = events[symbol]
        for i in range(days):
            open_time = start + timedelta(days=i)
            if i in sym_events:
                ev = sym_events[i]
                candles.append(
                    make_daily_candle(
                        symbol,
                        open_time,
                        ev.open_,
                        ev.high,
                        ev.low,
                        ev.close,
                        vol=ev.volume,
                    )
                )
            else:
                prev_close = candles[-1].close if candles else Decimal("100")
                candles.append(_flat(symbol, open_time, str(prev_close)))
        daily[symbol] = tuple(candles)

    weekly = {s: build_rising_weekly_series(s, 55).candles for s in SYMBOLS}
    monthly = {s: build_rising_monthly_series(s, 25).candles for s in SYMBOLS}
    return HistoricalDataBundle(daily=daily, weekly=weekly, monthly=monthly)


def reference_coverage_minimums() -> dict[str, int]:
    return {
        "evaluations": 250,
        "intents_created": 6,
        "entry_fills": 4,
        "positions_closed": 3,
        "trailing_stop_updates": 6,
        "gap_stops": 1,
        "intraday_stops": 1,
        "risk_rejections": 1,
        "duplicate_intents_suppressed": 1,
        "recoveries": 2,
        "restarts": 1,
        "degraded_periods": 1,
        "pause_periods": 1,
    }
