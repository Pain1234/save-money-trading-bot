"""Chronological walk-forward fold planning (P5-04 / #200).

Frozen Strategy V1 parameters are identical across folds. This module only
defines time boundaries — it does not optimize parameters.

**Purge / label embargo** and **feature warmup** are separate:

- ``embargo_days``: purge gap so evaluation labels are not adjacent to prior
  fold evaluation (label leakage control).
- ``feature_warmup_monthly_bars``: minimum **fully completed calendar months**
  in feature context before ``eval_start`` (Spec: monthly EMA-20 needs ≥20
  closed monthly candles). Partial edge months do not count. This is **not**
  interchangeable with a 90-day embargo or a fixed ``20 * 31`` day proxy.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

# Spec warmup: Monthly ≥ 20 closed monthly candles for EMA-20 monthly.
DEFAULT_FEATURE_WARMUP_MONTHLY_BARS = 20


@dataclass(frozen=True)
class WalkForwardFold:
    """One chronological evaluation fold with separated warmup vs embargo."""

    fold_id: str
    feature_context_start: date
    feature_context_end: date
    label_context_start: date
    label_context_end: date
    embargo_start: date
    embargo_end: date
    eval_start: date
    eval_end: date

    @property
    def context_start(self) -> date:
        """Alias: feature context start (backward-compatible name)."""

        return self.feature_context_start

    @property
    def context_end(self) -> date:
        """Alias: feature context end (backward-compatible name)."""

        return self.feature_context_end


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(UTC).date()
        return value.date()
    return value


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def count_completed_monthly_candles(context_start: date, context_end: date) -> int:
    """Count fully completed calendar months in ``[context_start, context_end]``.

    A month counts only when the entire month lies inside the context
    (``month_start >= context_start`` and ``month_end <= context_end``).
    Partial first/last months do not satisfy Spec monthly EMA warmup.
    """

    if context_end < context_start:
        return 0

    y, m = context_start.year, context_start.month
    if context_start.day != 1:
        y, m = _next_month(y, m)

    count = 0
    while True:
        start_m = _month_start(y, m)
        end_m = _month_end(y, m)
        if start_m > context_end:
            break
        if end_m > context_end:
            break
        if start_m >= context_start:
            count += 1
        y, m = _next_month(y, m)
    return count


def earliest_eval_start_for_monthly_warmup(
    range_start: date,
    *,
    monthly_bars: int,
) -> date:
    """Earliest ``eval_start`` with ``monthly_bars`` completed months before it."""

    if monthly_bars < 1:
        raise ValueError("monthly_bars must be >= 1")

    y, m = range_start.year, range_start.month
    if range_start.day != 1:
        y, m = _next_month(y, m)

    completed = 0
    while completed < monthly_bars:
        start_m = _month_start(y, m)
        end_m = _month_end(y, m)
        if start_m >= range_start:
            completed += 1
            if completed == monthly_bars:
                return end_m + timedelta(days=1)
        y, m = _next_month(y, m)
    raise RuntimeError("monthly warmup search failed")  # pragma: no cover


def plan_walk_forward_folds(
    *,
    range_start: date | datetime,
    range_end: date | datetime,
    n_folds: int,
    embargo_days: int,
    feature_warmup_monthly_bars: int = DEFAULT_FEATURE_WARMUP_MONTHLY_BARS,
    feature_warmup_days: int | None = None,
) -> list[WalkForwardFold]:
    """Split evaluation time into ``n_folds`` chronological windows.

    Evaluation windows tile ``[first_eval_start, range_end]`` where
    ``first_eval_start`` is the earliest date whose feature context
    ``[range_start, eval_start - 1]`` contains at least
    ``feature_warmup_monthly_bars`` **fully completed** calendar months.
    Optional ``feature_warmup_days`` adds a calendar-day floor on top of that.

    Label context ends ``embargo_days`` before ``eval_start`` (purge). Feature
    context may still include the embargo calendar window for indicator state;
    labels must not.
    """

    start = _as_date(range_start)
    end = _as_date(range_end)
    if end < start:
        raise ValueError("range_end must be >= range_start")
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if embargo_days < 0:
        raise ValueError("embargo_days must be >= 0")
    if feature_warmup_monthly_bars < 1:
        raise ValueError("feature_warmup_monthly_bars must be >= 1")
    if feature_warmup_days is not None and feature_warmup_days < 1:
        raise ValueError("feature_warmup_days must be >= 1 when set")

    first_eval_start = earliest_eval_start_for_monthly_warmup(
        start, monthly_bars=feature_warmup_monthly_bars
    )
    if feature_warmup_days is not None:
        first_eval_start = max(
            first_eval_start, start + timedelta(days=feature_warmup_days)
        )

    if first_eval_start > end:
        raise ValueError(
            "range too short for feature warmup before first eval "
            f"(need history through {first_eval_start.isoformat()}; "
            f"monthly_bars={feature_warmup_monthly_bars})"
        )

    total_days = (end - first_eval_start).days + 1
    if total_days < n_folds:
        raise ValueError("evaluable range shorter than n_folds after warmup")

    base = total_days // n_folds
    rem = total_days % n_folds
    folds: list[WalkForwardFold] = []
    cursor = first_eval_start
    for i in range(n_folds):
        length = base + (1 if i < rem else 0)
        eval_start = cursor
        eval_end = cursor + timedelta(days=length - 1)

        feature_context_start = start
        feature_context_end = eval_start - timedelta(days=1)
        completed = count_completed_monthly_candles(
            feature_context_start, feature_context_end
        )
        if completed < feature_warmup_monthly_bars:
            raise ValueError(
                f"fold {i + 1}: completed monthly candles {completed} < "
                f"feature_warmup_monthly_bars={feature_warmup_monthly_bars}"
            )
        if feature_warmup_days is not None:
            feature_span = (feature_context_end - feature_context_start).days + 1
            if feature_span < feature_warmup_days:
                raise ValueError(
                    f"fold {i + 1}: feature context span {feature_span}d < "
                    f"feature_warmup_days={feature_warmup_days}"
                )

        embargo_end = feature_context_end
        if embargo_days == 0:
            embargo_start = eval_start  # empty embargo window
            label_context_end = feature_context_end
        else:
            embargo_start = eval_start - timedelta(days=embargo_days)
            label_context_end = embargo_start - timedelta(days=1)

        label_context_start = start
        if label_context_end < label_context_start:
            raise ValueError(
                f"fold {i + 1}: embargo_days={embargo_days} leaves no label "
                "context before eval; widen range or reduce embargo"
            )

        folds.append(
            WalkForwardFold(
                fold_id=f"fold_{i + 1:02d}",
                feature_context_start=feature_context_start,
                feature_context_end=feature_context_end,
                label_context_start=label_context_start,
                label_context_end=label_context_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
                eval_start=eval_start,
                eval_end=eval_end,
            )
        )
        cursor = eval_end + timedelta(days=1)
    return folds
