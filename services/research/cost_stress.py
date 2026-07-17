"""Pre-registered cost stress scenarios (P5-05 / #201).

Scenarios are definitions only. Selecting the scenario that "just passes"
after seeing OOS results is forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CostStressScenario:
    name: str
    entry_fee_rate: Decimal
    exit_fee_rate: Decimal
    slippage_bps: Decimal
    funding_enabled: bool
    funding_assumed_rate: Decimal | None
    rationale: str


def default_p5_cost_stress_scenarios(
    *,
    base_fee: Decimal = Decimal("0.0005"),
    base_slippage_bps: Decimal = Decimal("5"),
) -> list[CostStressScenario]:
    """Return base / elevated / extreme fee, slippage, funding, and combined."""

    return [
        CostStressScenario(
            name="base",
            entry_fee_rate=base_fee,
            exit_fee_rate=base_fee,
            slippage_bps=base_slippage_bps,
            funding_enabled=False,
            funding_assumed_rate=None,
            rationale="P4 documented paper-like base assumptions",
        ),
        CostStressScenario(
            name="fee_x2",
            entry_fee_rate=base_fee * 2,
            exit_fee_rate=base_fee * 2,
            slippage_bps=base_slippage_bps,
            funding_enabled=False,
            funding_assumed_rate=None,
            rationale="Conservative fee doubling vs retail/VIP uncertainty",
        ),
        CostStressScenario(
            name="slippage_x2",
            entry_fee_rate=base_fee,
            exit_fee_rate=base_fee,
            slippage_bps=base_slippage_bps * 2,
            funding_enabled=False,
            funding_assumed_rate=None,
            rationale="Wider adverse selection / thin book",
        ),
        CostStressScenario(
            name="funding_stress",
            entry_fee_rate=base_fee,
            exit_fee_rate=base_fee,
            slippage_bps=base_slippage_bps,
            funding_enabled=True,
            funding_assumed_rate=Decimal("0.0001"),
            rationale="Modest daily funding drag while long (assumed_rate once/day)",
        ),
        CostStressScenario(
            name="combined_elevated",
            entry_fee_rate=base_fee * 2,
            exit_fee_rate=base_fee * 2,
            slippage_bps=base_slippage_bps * 2,
            funding_enabled=True,
            funding_assumed_rate=Decimal("0.0001"),
            rationale="Joint elevated fees, slippage, and funding",
        ),
        CostStressScenario(
            name="combined_extreme",
            entry_fee_rate=base_fee * 3,
            exit_fee_rate=base_fee * 3,
            slippage_bps=base_slippage_bps * 3,
            funding_enabled=True,
            funding_assumed_rate=Decimal("0.0003"),
            rationale="Extreme joint stress; informational unless base also fails",
        ),
    ]
