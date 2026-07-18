"""Explicit regime transition detection (Issue #285 / scorecard §5).

Directed transition ids require **calendar-adjacent** months. A missing
intervening month (e.g. Jan present, Feb absent, Mar present) breaks the
chain — no fabricated Jan→Mar transition and no TRANSITION_IN/OUT window
across the gap.

Day event tags (TRANSITION_IN/OUT) are **ex-post attribution** helpers once
adjacent period labels exist; they are not point-in-time signals.
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
    """Directed change between two **calendar-adjacent** months."""

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


@dataclass(frozen=True)
class CalendarGap:
    """Missing calendar month between two observed period labels."""

    after_period_id: str
    before_period_id: str
    missing_period_ids: tuple[str, ...]


def _parse_period_id(period_id: str) -> tuple[int, int]:
    year_s, month_s = period_id.split("-", 1)
    return int(year_s), int(month_s)


def _format_period_id(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _next_calendar_month(period_id: str) -> str:
    year, month = _parse_period_id(period_id)
    if month == 12:
        return _format_period_id(year + 1, 1)
    return _format_period_id(year, month + 1)


def months_are_calendar_adjacent(prev_id: str, cur_id: str) -> bool:
    """True iff ``cur_id`` is the immediate next calendar month after ``prev_id``."""
    return _next_calendar_month(prev_id) == cur_id


def missing_months_between(prev_id: str, cur_id: str) -> tuple[str, ...]:
    """Exclusive list of calendar months strictly between prev and cur."""
    if prev_id >= cur_id:
        return ()
    missing: list[str] = []
    cursor = _next_calendar_month(prev_id)
    # Bound iterations (never more than a few decades of months in research).
    for _ in range(240):
        if cursor >= cur_id:
            break
        missing.append(cursor)
        cursor = _next_calendar_month(cursor)
    return tuple(missing)


def detect_calendar_gaps(
    period_labels: Sequence[PeriodLabel],
) -> tuple[CalendarGap, ...]:
    """Report gaps between successive observed period labels."""
    gaps: list[CalendarGap] = []
    for prev, cur in zip(period_labels, period_labels[1:], strict=False):
        if months_are_calendar_adjacent(prev.period_id, cur.period_id):
            continue
        missing = missing_months_between(prev.period_id, cur.period_id)
        if missing:
            gaps.append(
                CalendarGap(
                    after_period_id=prev.period_id,
                    before_period_id=cur.period_id,
                    missing_period_ids=missing,
                )
            )
    return tuple(gaps)


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
    """Prefer trend-directed id; fall back to vol-directed id.

    Requires calendar adjacency when ``require_calendar_adjacency`` is set
    on the caller path (see :func:`detect_period_transitions`).
    """
    if prev.status != "OK" or cur.status != "OK":
        return None
    trend_id = _trend_transition_id(prev.trend, cur.trend)
    if trend_id is not None:
        return trend_id
    return _vol_transition_id(prev.vol, cur.vol)


def detect_period_transitions(
    period_labels: Sequence[PeriodLabel],
    *,
    require_calendar_adjacency: bool = True,
) -> tuple[PeriodTransition, ...]:
    """Emit transitions only for calendar-adjacent month pairs that change.

    Non-adjacent pairs (missing intervening months) are skipped entirely so
    Jan→Mar without Feb cannot invent ``BULL_TO_BEAR``.
    """
    out: list[PeriodTransition] = []
    for prev, cur in zip(period_labels, period_labels[1:], strict=False):
        if require_calendar_adjacency and not months_are_calendar_adjacent(
            prev.period_id, cur.period_id
        ):
            continue
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
    *,
    require_calendar_adjacency: bool = True,
) -> tuple[DayEventLabel, ...]:
    """Tag TRANSITION_IN / OUT / STABLE_REGIME using frozen window bars.

    Only calendar-adjacent transitions participate. Gaps yield no IN/OUT
    bridge across the missing month(s).
    """
    if len(bars) != len(day_labels):
        raise ValueError("bars and day_labels length mismatch")

    window = classifier.transition_window_bars
    by_period_bars: dict[str, list[PriceBar]] = {}
    for bar in bars:
        by_period_bars.setdefault(
            f"{bar.as_of.year:04d}-{bar.as_of.month:02d}", []
        ).append(bar)

    transitions = detect_period_transitions(
        period_labels,
        require_calendar_adjacency=require_calendar_adjacency,
    )
    transition_by_boundary = {
        (t.from_period_id, t.to_period_id): t.transition_id for t in transitions
    }

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
        is_out = day.period_id in out_periods and idx >= max(0, n - window)
        is_in = day.period_id in in_periods and idx < window

        if is_in and is_out:
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
