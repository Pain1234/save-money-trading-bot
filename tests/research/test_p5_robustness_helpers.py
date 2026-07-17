"""Tests for P5 robustness planning helpers (#200–#203)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.research.bootstrap import block_bootstrap_means, block_bootstrap_paths
from services.research.cost_stress import default_p5_cost_stress_scenarios
from services.research.parameter_stability import symmetric_neighborhood
from services.research.walk_forward import (
    DEFAULT_FEATURE_WARMUP_DAYS_MONTHLY_EMA_20,
    plan_walk_forward_folds,
)


def test_walk_forward_folds_are_chronological_and_cover_range() -> None:
    folds = plan_walk_forward_folds(
        range_start=date(2020, 1, 1),
        range_end=date(2024, 12, 31),
        n_folds=3,
        embargo_days=90,
        feature_warmup_days=DEFAULT_FEATURE_WARMUP_DAYS_MONTHLY_EMA_20,
    )
    assert len(folds) == 3
    assert folds[0].eval_start == date(2020, 1, 1) + timedelta(
        days=DEFAULT_FEATURE_WARMUP_DAYS_MONTHLY_EMA_20
    )
    assert folds[-1].eval_end == date(2024, 12, 31)
    for i in range(len(folds) - 1):
        assert folds[i].eval_end < folds[i + 1].eval_start


def test_walk_forward_separates_feature_warmup_from_label_embargo() -> None:
    folds = plan_walk_forward_folds(
        range_start=date(2020, 1, 1),
        range_end=date(2023, 12, 31),
        n_folds=2,
        embargo_days=90,
        feature_warmup_days=620,
    )
    fold = folds[0]
    assert fold.feature_context_start == date(2020, 1, 1)
    assert fold.feature_context_end == fold.eval_start - timedelta(days=1)
    assert (fold.feature_context_end - fold.feature_context_start).days + 1 >= 620
    assert fold.label_context_end < fold.embargo_start
    assert fold.embargo_end == fold.feature_context_end
    # Feature context includes the embargo calendar window; labels do not.
    assert fold.feature_context_end > fold.label_context_end


def test_walk_forward_rejects_empty_feature_context() -> None:
    with pytest.raises(ValueError, match="feature_warmup"):
        plan_walk_forward_folds(
            range_start=date(2024, 1, 1),
            range_end=date(2024, 3, 31),
            n_folds=3,
            embargo_days=7,
            feature_warmup_days=620,
        )


def test_block_bootstrap_paths_expose_net_pnl_and_drawdown_quantiles() -> None:
    series = [0.01, -0.02, 0.015, 0.0, -0.005, 0.02, 0.01, -0.01]
    a = block_bootstrap_paths(series, block_length=2, n_simulations=50, seed=42)
    b = block_bootstrap_paths(series, block_length=2, n_simulations=50, seed=42)
    assert a.net_pnl_quantiles == b.net_pnl_quantiles
    assert a.max_drawdown_quantiles == b.max_drawdown_quantiles
    assert "q05" in a.net_pnl_quantiles
    assert "q05" in a.max_drawdown_quantiles
    assert a.max_drawdown_quantiles["q05"] <= 0.0


def test_block_bootstrap_means_is_deterministic_for_seed() -> None:
    series = [0.01, -0.02, 0.015, 0.0, -0.005, 0.02]
    a = block_bootstrap_means(series, block_length=2, n_simulations=50, seed=42)
    b = block_bootstrap_means(series, block_length=2, n_simulations=50, seed=42)
    assert a.quantiles == b.quantiles
    assert a.mean == b.mean
    assert "q05" in a.quantiles


def test_parameter_neighborhood_keeps_frozen_and_neighbors() -> None:
    frozen = {
        "daily_ema_period": 20,
        "breakout_lookback": 20,
        "atr_period": 14,
        "stop_initial_atr_mult": "2.5",
        "trail_atr_mult": "3.0",
        "pullback_ema_tolerance": "0.005",
    }
    variants = symmetric_neighborhood(frozen)
    assert variants[0] == frozen
    assert len(variants) > 1
    assert any(v["daily_ema_period"] == 18 for v in variants)


def test_cost_stress_scenarios_include_base_and_combined() -> None:
    scenarios = default_p5_cost_stress_scenarios()
    names = {s.name for s in scenarios}
    assert "base" in names
    assert "combined_elevated" in names
    assert "combined_extreme" in names
    base = next(s for s in scenarios if s.name == "base")
    assert base.entry_fee_rate == Decimal("0.0005")
