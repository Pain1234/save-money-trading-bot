"""Robustness test orchestration helpers (Issue #247 / P4.7b).

Wires the existing P5 diagnostic helpers — walk-forward fold planning
(:mod:`research.walk_forward`), cost stress scenarios
(:mod:`research.cost_stress`), parameter-neighborhood variants
(:mod:`research.parameter_stability`), and block bootstrap
(:mod:`research.bootstrap`) — onto the SAME research runner / registry /
artifact line used by the Strategy Lab (Issue #242). This module only
*builds* child ``ExperimentSpec`` instances (for walk_forward / cost_stress /
parameter_stability); those child Specs are executed through the existing
:func:`research.runner.run_experiment` by the orchestration service
(:mod:`research.robustness_service`). Bootstrap does not spawn child runs —
it post-processes an already-completed run's ``equity.json`` artifact.

There is no second backtest engine here and no private Strategy V1 numbers:
this module is pure computation over Specs/artifacts already produced by the
existing pipeline. See
``docs/project-management/p4-research-workspace-follow-ups.md``.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from datetime import time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from research.bootstrap import PathBootstrapResult, block_bootstrap_paths
from research.cost_stress import CostStressScenario, default_p5_cost_stress_scenarios
from research.experiment_spec import (
    ExperimentSpec,
    FeeAssumption,
    FundingAssumption,
    SlippageAssumption,
    TimeRange,
)
from research.parameter_stability import symmetric_neighborhood
from research.walk_forward import (
    DEFAULT_FEATURE_WARMUP_MONTHLY_BARS,
    plan_walk_forward_folds,
)

RobustnessTestType = Literal[
    "walk_forward", "cost_stress", "parameter_stability", "bootstrap"
]
ROBUSTNESS_TEST_TYPES: tuple[RobustnessTestType, ...] = (
    "walk_forward",
    "cost_stress",
    "parameter_stability",
    "bootstrap",
)
ROBUSTNESS_MANIFEST_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RobustnessChildSpec:
    """One child ``ExperimentSpec`` derived from a base run for orchestrated execution."""

    child_id: str
    label: str
    spec: ExperimentSpec


def _day_start(value: date) -> datetime:
    return datetime.combine(value, dtime.min, tzinfo=UTC)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, dtime(23, 59, 59), tzinfo=UTC)


def build_walk_forward_child_specs(
    base_spec: ExperimentSpec,
    *,
    n_folds: int,
    embargo_days: int,
    feature_warmup_monthly_bars: int = DEFAULT_FEATURE_WARMUP_MONTHLY_BARS,
) -> list[RobustnessChildSpec]:
    """One child Spec per walk-forward fold (feature-context start .. eval end).

    Reuses ``plan_walk_forward_folds`` for chronological boundaries only.
    Frozen Strategy V1 parameters are identical across folds — this is not
    parameter optimization (P5-04).
    """

    folds = plan_walk_forward_folds(
        range_start=base_spec.time_range.start,
        range_end=base_spec.time_range.end,
        n_folds=n_folds,
        embargo_days=embargo_days,
        feature_warmup_monthly_bars=feature_warmup_monthly_bars,
    )
    children: list[RobustnessChildSpec] = []
    for fold in folds:
        time_range = TimeRange(
            start=_day_start(fold.feature_context_start),
            end=_day_end(fold.eval_end),
        )
        child_spec = base_spec.model_copy(
            update={
                "time_range": time_range,
                "hypothesis": f"{base_spec.hypothesis} [walk_forward:{fold.fold_id}]",
            }
        )
        children.append(
            RobustnessChildSpec(child_id=fold.fold_id, label=fold.fold_id, spec=child_spec)
        )
    return children


def _cost_scenario_to_assumptions(
    scenario: CostStressScenario,
    *,
    fee_model_version: str,
    slippage_model_version: str,
    funding_model_version: str,
) -> tuple[FeeAssumption, SlippageAssumption, FundingAssumption]:
    fee = FeeAssumption(
        entry_fee_rate=scenario.entry_fee_rate,
        exit_fee_rate=scenario.exit_fee_rate,
        model_version=fee_model_version,
    )
    slip = SlippageAssumption(
        slippage_bps=scenario.slippage_bps,
        model_version=slippage_model_version,
    )
    funding = FundingAssumption(
        enabled=scenario.funding_enabled,
        assumed_rate=scenario.funding_assumed_rate,
        model_version=funding_model_version,
    )
    return fee, slip, funding


def build_cost_stress_child_specs(base_spec: ExperimentSpec) -> list[RobustnessChildSpec]:
    """One child Spec per pre-registered P5 cost stress scenario (P5-05).

    Base fee/slippage/funding come from the frozen ``base_spec`` (the Spec
    stays the single source of cost truth; scenarios only elevate on top).
    Scenarios are definitions only — selecting the one that "just passes"
    after seeing results is out of scope for this orchestrator.
    """

    scenarios = default_p5_cost_stress_scenarios(
        base_fee=base_spec.fee_assumption.entry_fee_rate,
        base_slippage_bps=base_spec.slippage_assumption.slippage_bps,
        base_funding_enabled=base_spec.funding_assumption.enabled,
        base_funding_assumed_rate=base_spec.funding_assumption.assumed_rate,
    )
    children: list[RobustnessChildSpec] = []
    for scenario in scenarios:
        fee, slip, funding = _cost_scenario_to_assumptions(
            scenario,
            fee_model_version=base_spec.fee_assumption.model_version,
            slippage_model_version=base_spec.slippage_assumption.model_version,
            funding_model_version=base_spec.funding_assumption.model_version,
        )
        child_spec = base_spec.model_copy(
            update={
                "fee_assumption": fee,
                "slippage_assumption": slip,
                "funding_assumption": funding,
                "hypothesis": f"{base_spec.hypothesis} [cost_stress:{scenario.name}]",
            }
        )
        children.append(
            RobustnessChildSpec(
                child_id=scenario.name, label=scenario.rationale, spec=child_spec
            )
        )
    return children


def _param_variant_label(base: dict[str, Any], variant: dict[str, Any]) -> str:
    changed = [
        f"{key}={variant[key]}"
        for key in sorted(variant)
        if key != "strategy_id" and variant.get(key) != base.get(key)
    ]
    return "baseline" if not changed else ",".join(changed)


def build_parameter_stability_child_specs(
    base_spec: ExperimentSpec,
    *,
    int_deltas: dict[str, tuple[int, ...]] | None = None,
    decimal_relative_steps: dict[str, tuple[str, ...]] | None = None,
) -> list[RobustnessChildSpec]:
    """One child Spec per one-at-a-time parameter neighbor (P5-06, diagnostic only).

    Successful neighbors must not replace a failed frozen candidate — this
    orchestrator only records neighbor run results for inspection.
    """

    variants = symmetric_neighborhood(
        dict(base_spec.parameters),
        int_deltas=int_deltas,
        decimal_relative_steps=decimal_relative_steps,
    )
    base_params = dict(base_spec.parameters)
    children: list[RobustnessChildSpec] = []
    for index, variant in enumerate(variants):
        label = _param_variant_label(base_params, variant)
        child_id = "frozen" if index == 0 else f"neighbor_{index:02d}"
        child_spec = base_spec.model_copy(
            update={
                "parameters": variant,
                "hypothesis": f"{base_spec.hypothesis} [parameter_stability:{child_id}]",
            }
        )
        children.append(RobustnessChildSpec(child_id=child_id, label=label, spec=child_spec))
    return children


def period_pnl_series_from_equity(equity_points: list[dict[str, Any]]) -> list[float]:
    """Chronological net-PnL increments derived from a run's ``equity.json``.

    No second engine: reuses the equity curve already produced by
    ``run_experiment`` for the base run. Public/synthetic fixtures only.
    """

    rows = [
        row
        for row in equity_points
        if isinstance(row, dict) and row.get("equity") is not None
    ]
    rows.sort(key=lambda row: str(row.get("time") or ""))
    equities = [Decimal(str(row["equity"])) for row in rows]
    return [float(b - a) for a, b in zip(equities[:-1], equities[1:], strict=False)]


def compute_bootstrap_from_equity_artifact(
    artifact_path: Path,
    *,
    block_length: int,
    n_simulations: int,
    seed: int,
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95),
) -> PathBootstrapResult:
    """Block-bootstrap (P5-07) over a completed run's period net-PnL series.

    Raises ``ValueError`` (propagated from :func:`block_bootstrap_paths`) on
    samples too small for meaningful blocks — callers must record N/A rather
    than false confidence.
    """

    equity_path = artifact_path / "equity.json"
    if not equity_path.is_file():
        msg = f"equity.json missing for bootstrap source run: {artifact_path}"
        raise FileNotFoundError(msg)
    equity_points = json.loads(equity_path.read_text(encoding="utf-8"))
    if not isinstance(equity_points, list):
        msg = "equity.json must be a list"
        raise ValueError(msg)
    series = period_pnl_series_from_equity(equity_points)
    return block_bootstrap_paths(
        series,
        block_length=block_length,
        n_simulations=n_simulations,
        seed=seed,
        quantiles=quantiles,
    )


def robustness_root(root: Path) -> Path:
    return root / "artifacts" / "research" / "robustness"


def robustness_artifact_dir(root: Path, robustness_id: str) -> Path:
    return robustness_root(root) / robustness_id


def robustness_manifest_path(root: Path, robustness_id: str) -> Path:
    return robustness_artifact_dir(root, robustness_id) / "manifest.json"


def compute_robustness_id(
    *,
    base_experiment_id: str,
    test_type: str,
    config: dict[str, Any],
    dataset_catalog_id: str | None = None,
    base_run_id: str | None = None,
) -> str:
    """Deterministic robustness_id — idempotent create, mirrors experiment_id."""

    payload = {
        "base_experiment_id": base_experiment_id,
        "base_run_id": base_run_id,
        "test_type": test_type,
        "dataset_catalog_id": dataset_catalog_id,
        "config": config,
    }
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"rob_{digest}"


@dataclass(frozen=True)
class RobustnessChildResult:
    """One executed child result recorded in the robustness manifest artifact."""

    child_id: str
    label: str
    experiment_id: str | None
    run_id: str | None
    status: str
    net_pnl: str | None = None
    max_drawdown: str | None = None
    closed_trades: int | None = None
    profit_factor: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RobustnessManifest:
    """Artifact per robustness test — status + results + gate evaluator hook (#248).

    ``manifest.json`` under ``artifacts/research/robustness/{robustness_id}/``
    is the stable artifact path a future gate evaluator can bind to. This
    issue implements the hook point only; gate persistence itself is #248.
    """

    schema_version: str
    robustness_id: str
    test_type: str
    base_experiment_id: str
    base_run_id: str | None
    dataset_catalog_id: str | None
    config: dict[str, Any]
    created_at: str
    children: tuple[RobustnessChildResult, ...]
    bootstrap_result: dict[str, Any] | None
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "robustness_id": self.robustness_id,
            "test_type": self.test_type,
            "base_experiment_id": self.base_experiment_id,
            "base_run_id": self.base_run_id,
            "dataset_catalog_id": self.dataset_catalog_id,
            "config": self.config,
            "created_at": self.created_at,
            "children": [c.to_dict() for c in self.children],
            "bootstrap_result": self.bootstrap_result,
            "summary": self.summary,
        }


def save_robustness_manifest(root: Path, manifest: RobustnessManifest) -> Path:
    """Atomic write of the per-test artifact (temp file + ``os.replace``)."""

    path = robustness_manifest_path(root, manifest.robustness_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    data = json.dumps(manifest.to_dict(), sort_keys=True, indent=2) + "\n"
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def load_robustness_manifest(root: Path, robustness_id: str) -> dict[str, Any] | None:
    path = robustness_manifest_path(root, robustness_id)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return raw
