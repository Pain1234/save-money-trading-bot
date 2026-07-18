"""Explicit regime transition detection (Issue #285 / scorecard §5).

Directed transition ids are deterministic functions of adjacent period labels.
Day-level event tags use a fixed bar window at the month boundary — no
look-ahead beyond the already-computed period labels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from research.regime.classifier import RegimeClassifier
from research.regime.labeling import DayLabel, PeriodLabel, PriceBar
from research.regime.taxonomy import EventLabel, TrendLabel, VolLabel


@dataclass(frozen=True)
class PeriodTransition:
    """Directed change between two consecutive calendar months."""

    from_period_id: str
    to_period_id: str
    from_trend: TrendLabel
    to_trend: TrendLabel
    from_vol: VolLabel
    to_vol: VolLabel
    transition_id: str
    trend_changed: bool
    vol_changed: bool


@dataclass(frozen=True)
class DayEventLabel:
    """Per-day event layer relative to adjacent period transitions."""

    as_of: date
    period_id: str
    event: EventLabel
    transition_id: str | None


def _trend_transition_id(prev: TrendLabel, cur: TrendLabel) -> str | None:
    if prev == cur or prev == "INSUFFICIENT" or cur == "INSUFFICIENT":
        return None
    if prev in ("BULL", "BEAR") and cur == "SIDEWAYS":
        return "TREND_TO_SIDEWAYS"
    if prev == "SIDEWAYS" and cur in ("BULL", "BEAR"):
        return "SIDEWAYS_TO_TREND"
    return f"{prev}_TO_{cur}"


def _vol_transition_id(prev: VolLabel, cur: VolLabel) -> str | None:
    if prev == cur or prev == "INSUFFICIENT" or cur == "INSUFFICIENT":
        return None
    mapping = {
        ("LOW_VOL", "HIGH_VOL"): "LOW_TO_HIGH_VOL",
        ("HIGH_VOL", "LOW_VOL"): "HIGH_TO_LOW_VOL",
        ("LOW_VOL", "NORMAL_VOL"): "LOW_TO_NORMAL_VOL",
        ("NORMAL_VOL", "LOW_VOL"): "NORMAL_TO_LOW_VOL",
        ("NORMAL_VOL", "HIGH_VOL"): "NORMAL_TO_HIGH_VOL",
        ("HIGH_VOL", "NORMAL_VOL"): "HIGH_TO_NORMAL_VOL",
    }
    return mapping.get((prev, cur), f"{prev}_TO_{cur}")


def directed_transition_id(
    prev: PeriodLabel, cur: PeriodLabel
) -> str | None:
    """Prefer trend-directed id; fall back to vol-directed id."""
    if prev.status != "OK" or cur.status != "OK":
        return None
    trend_id = _trend_transition_id(prev.trend, cur.trend)
    if trend_id is not None:
        return trend_id
    return _vol_transition_id(prev.vol, cur.vol)


def detect_period_transitions(
    period_labels: Sequence[PeriodLabel],
) -> tuple[PeriodTransition, ...]:
    """Emit one record per adjacent month pair that actually changes."""
    out: list[PeriodTransition] = []
    for prev, cur in zip(period_labels, period_labels[1:], strict=False):
        tid = directed_transition_id(prev, cur)
        if tid is None:
            continue
        out.append(
            PeriodTransition(
                from_period_id=prev.period_id,
                to_period_id=cur.period_id,
                from_trend=prev.trend,
                to_trend=cur.trend,
                from_vol=prev.vol,
                to_vol=cur.vol,
                transition_id=tid,
                trend_changed=prev.trend != cur.trend,
                vol_changed=prev.vol != cur.vol,
            )
        )
    return tuple(out)


def label_day_events(
    bars: Sequence[PriceBar],
    day_labels: Sequence[DayLabel],
    period_labels: Sequence[PeriodLabel],
    classifier: RegimeClassifier,
) -> tuple[DayEventLabel, ...]:
    """Tag TRANSITION_IN / OUT / STABLE_REGIME using frozen window bars."""
    if len(bars) != len(day_labels):
        raise ValueError("bars and day_labels length mismatch")

    window = classifier.transition_window_bars
    by_period_bars: dict[str, list[PriceBar]] = {}
    for bar in bars:
        by_period_bars.setdefault(
            f"{bar.as_of.year:04d}-{bar.as_of.month:02d}", []
        ).append(bar)

    transition_by_boundary: dict[tuple[str, str], str] = {}
    for prev, cur in zip(period_labels, period_labels[1:], strict=False):
        tid = directed_transition_id(prev, cur)
        if tid is not None:
            transition_by_boundary[(prev.period_id, cur.period_id)] = tid

    # Periods that exit into a changed next month / enter from a changed prev.
    out_periods = {a for (a, _b) in transition_by_boundary}
    in_periods = {b for (_a, b) in transition_by_boundary}
    tid_out = {a: tid for (a, _b), tid in transition_by_boundary.items()}
    tid_in = {b: tid for (_a, b), tid in transition_by_boundary.items()}

    out: list[DayEventLabel] = []
    for bar, day in zip(bars, day_labels, strict=True):
        if day.status != "OK":
            out.append(
                DayEventLabel(
                    as_of=bar.as_of,
                    period_id=day.period_id,
                    event="INSUFFICIENT",
                    transition_id=None,
                )
            )
            continue

        period_bars = by_period_bars[day.period_id]
        idx = next(
            i for i, b in enumerate(period_bars) if b.as_of == bar.as_of
        )
        n = len(period_bars)
        is_out = (
            day.period_id in out_periods and idx >= max(0, n - window)
        )
        is_in = day.period_id in in_periods and idx < window

        if is_in and is_out:
            # Rare short month: prefer OUT at the end, IN at the start.
            if idx < n / 2:
                event: EventLabel = "TRANSITION_IN"
                tid = tid_in.get(day.period_id)
            else:
                event = "TRANSITION_OUT"
                tid = tid_out.get(day.period_id)
        elif is_in:
            event = "TRANSITION_IN"
            tid = tid_in.get(day.period_id)
        elif is_out:
            event = "TRANSITION_OUT"
            tid = tid_out.get(day.period_id)
        else:
            event = "STABLE_REGIME"
            tid = None

        out.append(
            DayEventLabel(
                as_of=bar.as_of,
                period_id=day.period_id,
                event=event,
                transition_id=tid,
            )
        )
    return tuple(out)
