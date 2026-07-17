"""Chronological walk-forward fold planning (P5-04 / #200).

Frozen Strategy V1 parameters are identical across folds. This module only
defines time boundaries and embargo gaps — it does not optimize parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True)
class WalkForwardFold:
    """One chronological evaluation fold."""

    fold_id: str
    context_start: date
    context_end: date
    eval_start: date
    eval_end: date


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).date()
        return value.date()
    return value


def plan_walk_forward_folds(
    *,
    range_start: date | datetime,
    range_end: date | datetime,
    n_folds: int,
    embargo_days: int,
) -> list[WalkForwardFold]:
    """Split ``[range_start, range_end]`` into ``n_folds`` eval windows.

    Each fold uses all prior history in-range as context (expanding), then an
    embargo gap, then a contiguous eval segment. Folds are chronological;
    parameters are not inputs (caller must keep Spec frozen).
    """

    start = _as_date(range_start)
    end = _as_date(range_end)
    if end < start:
        raise ValueError("range_end must be >= range_start")
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if embargo_days < 0:
        raise ValueError("embargo_days must be >= 0")

    total_days = (end - start).days + 1
    if total_days < n_folds:
        raise ValueError("range shorter than n_folds")

    base = total_days // n_folds
    rem = total_days % n_folds
    folds: list[WalkForwardFold] = []
    cursor = start
    for i in range(n_folds):
        length = base + (1 if i < rem else 0)
        eval_start = cursor
        eval_end = cursor + timedelta(days=length - 1)
        context_end = eval_start - timedelta(days=1 + embargo_days)
        context_start = start
        if context_end < context_start:
            # First fold or heavy embargo: empty context allowed; caller decides.
            context_end = context_start - timedelta(days=1)
        folds.append(
            WalkForwardFold(
                fold_id=f"fold_{i + 1:02d}",
                context_start=context_start,
                context_end=context_end,
                eval_start=eval_start,
                eval_end=eval_end,
            )
        )
        cursor = eval_end + timedelta(days=1)
    return folds
