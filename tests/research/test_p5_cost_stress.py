"""Tests for P5 cost-stress scenarios (#201)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.research.cost_stress import default_p5_cost_stress_scenarios


def test_cost_stress_scenarios_include_base_and_combined() -> None:
    scenarios = default_p5_cost_stress_scenarios()
    names = {s.name for s in scenarios}
    assert "base" in names
    assert "combined_elevated" in names
    assert "combined_extreme" in names
    base = next(s for s in scenarios if s.name == "base")
    assert base.entry_fee_rate == Decimal("0.0005")
    assert base.funding_enabled is False
    assert base.funding_assumed_rate is None


def test_base_scenario_mirrors_spec_funding_when_enabled() -> None:
    scenarios = default_p5_cost_stress_scenarios(
        base_funding_enabled=True,
        base_funding_assumed_rate=Decimal("0.00005"),
    )
    base = next(s for s in scenarios if s.name == "base")
    assert base.funding_enabled is True
    assert base.funding_assumed_rate == Decimal("0.00005")
    fee_x2 = next(s for s in scenarios if s.name == "fee_x2")
    assert fee_x2.funding_enabled is True
    assert fee_x2.funding_assumed_rate == Decimal("0.00005")


def test_base_funding_enabled_requires_assumed_rate() -> None:
    with pytest.raises(ValueError, match="base_funding_assumed_rate"):
        default_p5_cost_stress_scenarios(base_funding_enabled=True)
