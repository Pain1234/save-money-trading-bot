"""Tests for P5 block-bootstrap path uncertainty (#203)."""

from __future__ import annotations

import pytest

from services.research.bootstrap import block_bootstrap_means, block_bootstrap_paths


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


def test_bootstrap_rejects_single_point_series() -> None:
    with pytest.raises(ValueError, match="too short|N/A"):
        block_bootstrap_paths([0.01], block_length=1, n_simulations=10, seed=1)


def test_bootstrap_rejects_block_length_covering_full_series() -> None:
    series = [0.01, -0.02, 0.015]
    with pytest.raises(ValueError, match="block_length must be < len"):
        block_bootstrap_paths(series, block_length=3, n_simulations=10, seed=1)
    with pytest.raises(ValueError, match="block_length must be < len"):
        block_bootstrap_means(series, block_length=3, n_simulations=10, seed=1)
