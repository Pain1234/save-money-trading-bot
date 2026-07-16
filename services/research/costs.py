"""Cost-model enforcement and Spec → BacktestConfig mapping (Issue #49 / R-005)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from backtester.models import FeeModel, FundingModel, SlippageModel
from pydantic import BaseModel, ConfigDict, Field

from research.experiment_spec import ExperimentSpec

COST_MODEL_VERSION = "1.0"


class CostScenario(BaseModel):
    """Named cost variant declared on an experiment (no P5 stress evaluation)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    fee_model_version: str = Field(default=COST_MODEL_VERSION)
    slippage_model_version: str = Field(default=COST_MODEL_VERSION)
    funding_model_version: str = Field(default=COST_MODEL_VERSION)
    entry_fee_rate: Decimal = Field(ge=Decimal("0"))
    exit_fee_rate: Decimal = Field(ge=Decimal("0"))
    slippage_bps: Decimal = Field(ge=Decimal("0"))
    funding_enabled: bool = False
    funding_assumed_rate: Decimal | None = None


def require_cost_fields(spec: ExperimentSpec) -> None:
    """Fail closed if mandatory cost assumptions are missing or incomplete."""
    fee = spec.fee_assumption
    slip = spec.slippage_assumption
    funding = spec.funding_assumption
    if fee.entry_fee_rate is None or fee.exit_fee_rate is None:
        msg = "fee_assumption rates are required"
        raise ValueError(msg)
    if not fee.model_version.strip():
        msg = "fee_assumption.model_version is required"
        raise ValueError(msg)
    if slip.slippage_bps is None:
        msg = "slippage_assumption.slippage_bps is required"
        raise ValueError(msg)
    if not slip.model_version.strip():
        msg = "slippage_assumption.model_version is required"
        raise ValueError(msg)
    if not funding.model_version.strip():
        msg = "funding_assumption.model_version is required"
        raise ValueError(msg)
    if funding.enabled and funding.assumed_rate is None:
        msg = "funding_assumption.assumed_rate required when funding enabled"
        raise ValueError(msg)


def cost_models_from_spec(
    spec: ExperimentSpec,
) -> tuple[FeeModel, SlippageModel, FundingModel]:
    """Map ExperimentSpec cost assumptions to backtester models."""
    require_cost_fields(spec)
    fee = FeeModel(
        entry_fee_rate=spec.fee_assumption.entry_fee_rate,
        exit_fee_rate=spec.fee_assumption.exit_fee_rate,
    )
    slip = SlippageModel(slippage_bps=spec.slippage_assumption.slippage_bps)
    funding = FundingModel(
        enabled=spec.funding_assumption.enabled,
        assumed_rate=spec.funding_assumption.assumed_rate,
    )
    return fee, slip, funding


def base_cost_scenario(spec: ExperimentSpec) -> CostScenario:
    """Declare the base named cost scenario from Spec fields."""
    require_cost_fields(spec)
    return CostScenario(
        name="base",
        fee_model_version=spec.fee_assumption.model_version,
        slippage_model_version=spec.slippage_assumption.model_version,
        funding_model_version=spec.funding_assumption.model_version,
        entry_fee_rate=spec.fee_assumption.entry_fee_rate,
        exit_fee_rate=spec.fee_assumption.exit_fee_rate,
        slippage_bps=spec.slippage_assumption.slippage_bps,
        funding_enabled=spec.funding_assumption.enabled,
        funding_assumed_rate=spec.funding_assumption.assumed_rate,
    )


def cost_manifest_fields(spec: ExperimentSpec) -> dict[str, Any]:
    """Versioned cost pins for RunManifest / costs.json artifact."""
    require_cost_fields(spec)
    scenario = base_cost_scenario(spec)
    named = [s.name for s in spec.cost_scenarios]
    return {
        "cost_model_version": COST_MODEL_VERSION,
        "fee_model_version": scenario.fee_model_version,
        "slippage_model_version": scenario.slippage_model_version,
        "funding_model_version": scenario.funding_model_version,
        "cost_scenario": scenario.name,
        "named_cost_scenarios": named,
        "funding_assumed_rate": (
            format(scenario.funding_assumed_rate, "f")
            if scenario.funding_assumed_rate is not None
            else None
        ),
        "funding_semantics": (
            "assumed_rate_per_daily_candle"
            if scenario.funding_enabled
            else "disabled"
        ),
        "gross_net_required": True,
        "gross_pnl_identity": "net + fees + slippage + funding_costs",
    }
