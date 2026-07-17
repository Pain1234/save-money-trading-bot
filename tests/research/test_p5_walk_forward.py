"""Tests for P5 walk-forward fold planning (#200)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.research.walk_forward import (
    count_completed_monthly_candles,
    earliest_eval_start_for_monthly_warmup,
    plan_walk_forward_folds,
)


def test_completed_monthly_candles_skip_partial_edge_months() -> None:
    assert count_completed_monthly_candles(date(2020, 1, 2), date(2021, 9, 12)) == 19
    assert count_completed_monthly_candles(date(2020, 1, 2), date(2021, 9, 30)) == 20
    assert earliest_eval_start_for_monthly_warmup(date(2020, 1, 2), monthly_bars=20) == date(2021, 10, 1)


def test_walk_forward_folds_are_chronological_and_cover_range() -> None:
    folds = plan_walk_forward_folds(
        range_start=date(2020, 1, 1),
        range_end=date(2024, 12, 31),
        n_folds=3,
        embargo_days=90,
        feature_warmup_monthly_bars=20,
    )
    assert len(folds) == 3
    assert folds[0].eval_start == date(2021, 9, 1)
    assert folds[-1].eval_end == date(2024, 12, 31)
    for i in range(len(folds) - 1):
        assert folds[i].eval_end < folds[i + 1].eval_start


def test_walk_forward_rejects_620_day_proxy_that_yields_only_19_months() -> None:
    proxy_eval = date(2020, 1, 2) + timedelta(days=620)
    assert proxy_eval == date(2021, 9, 13)
    assert count_completed_monthly_candles(date(2020, 1, 2), proxy_eval - timedelta(days=1)) == 19
    folds = plan_walk_forward_folds(
        range_start=date(2020, 1, 2),
        range_end=date(2024, 12, 31),
        n_folds=2,
        embargo_days=90,
        feature_warmup_monthly_bars=20,
    )
    assert folds[0].eval_start == date(2021, 10, 1)
    assert count_completed_monthly_candles(folds[0].feature_context_start, folds[0].feature_context_end) >= 20


def test_walk_forward_separates_feature_warmup_from_label_embargo() -> None:
    folds = plan_walk_forward_folds(
        range_start=date(2020, 1, 1),
        range_end=date(2023, 12, 31),
        n_folds=2,
        embargo_days=90,
        feature_warmup_monthly_bars=20,
    )
    fold = folds[0]
    assert fold.feature_context_end == fold.eval_start - timedelta(days=1)
    assert fold.label_context_end < fold.embargo_start
    assert fold.feature_context_end > fold.label_context_end


def test_walk_forward_rejects_insufficient_monthly_warmup() -> None:
    with pytest.raises(ValueError, match="feature warmup|monthly"):
        plan_walk_forward_folds(
            range_start=date(2024, 1, 1),
            range_end=date(2024, 3, 31),
            n_folds=3,
            embargo_days=7,
            feature_warmup_monthly_bars=20,
        )
