"""Tests for P5 parameter neighborhood diagnostics (#202)."""

from __future__ import annotations

from services.research.parameter_stability import symmetric_neighborhood


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
