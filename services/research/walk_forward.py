"""Chronological walk-forward fold planning (P5-04 / #200).

Frozen Strategy V1 parameters are identical across folds. This module only
defines time boundaries — it does not optimize parameters.

**Purge / label embargo** and **feature warmup** are separate:

- ``embargo_days``: purge gap so evaluation labels are not adjacent to prior
  fold evaluation (label leakage control).
- ``feature_warmup_days``: minimum calendar history required *before*
  ``eval_start`` so indicators (e.g. monthly EMA-20 ≈ 20 monthly bars) can
  form. This is **not** interchangeable with a 90-day embargo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

# Upper-bound calendar span for ~20 completed monthly bars (EMA-20 monthly).
# Spec warmup: Monthly ≥ 20. 20 * 31 days is intentional slack, not a 90-day proxy.
DEFAULT_FEATURE_WARMUP_DAYS_MONTHLY_EMA_20 = 20 * 31


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
            return value.astimezone(timezone.utc).date()
        return value.date()
    return value


def plan_walk_forward_folds(
    *,
    range_start: date | datetime,
    range_end: date | datetime,
    n_folds: int,
    embargo_days: int,
    feature_warmup_days: int = DEFAULT_FEATURE_WARMUP_DAYS_MONTHLY_EMA_20,
) -> list[WalkForwardFold]:
    """Split evaluation time into ``n_folds`` chronological windows.

    Evaluation windows tile ``[range_start + feature_warmup_days, range_end]``.
    Feature context for each fold is ``[range_start, eval_start - 1]`` and must
    span at least ``feature_warmup_days`` calendar days (inclusive count of
    days from ``feature_context_start`` through ``feature_context_end``).

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
    if feature_warmup_days < 1:
        raise ValueError("feature_warmup_days must be >= 1")

    first_eval_start = start + timedelta(days=feature_warmup_days)
    if first_eval_start > end:
        raise ValueError(
            "range too short for feature_warmup_days before first eval "
            f"(need history through {first_eval_start.isoformat()})"
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
