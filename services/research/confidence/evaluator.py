"""Evidence confidence evaluator (#288).

Derives HIGH/MEDIUM/LOW/INSUFFICIENT/NOT_AVAILABLE from measurable inputs.
Never accepts a free-form manual confidence override. Does not write to the
gate registry and performs no auto-promotion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from research.confidence.inputs import (
    ConfidenceEvidenceInputs,
    ConfidenceLimitation,
    build_limitations,
)
from research.confidence.policy import (
    ConfidenceDimensionFloors,
    ConfidenceLabel,
    ConfidencePolicy,
    ConfidencePolicyError,
    compute_confidence_policy_content_hash,
    get_confidence_policy,
    label_from_count,
    worse_label,
)

CONFIDENCE_PROFILE_FILENAME = "confidence_profile.json"
CONFIDENCE_PROFILE_SCHEMA_VERSION = "1.0"


class ConfidenceEvaluationError(Exception):
    """Inputs could not be evaluated fail-closed."""


@dataclass(frozen=True)
class DimensionResult:
    name: str
    label: ConfidenceLabel
    required: bool
    measured_value: str | None
    reason: str
    raw_inputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "measured_value": self.measured_value,
            "name": self.name,
            "raw_inputs": dict(sorted(self.raw_inputs.items(), key=lambda kv: kv[0])),
            "reason": self.reason,
            "required": self.required,
        }


@dataclass(frozen=True)
class ConfidenceResult:
    confidence_id: str
    schema_version: str
    policy_version: str
    policy_content_hash: str
    overall_label: ConfidenceLabel
    overall_reason: str
    dimensions: tuple[DimensionResult, ...]
    limitations: tuple[ConfidenceLimitation, ...]
    inputs_summary: dict[str, Any]
    decision_binding: bool = False
    auto_promotion: bool = False

    def to_artifact(self) -> dict[str, Any]:
        return {
            "auto_promotion": self.auto_promotion,
            "confidence_id": self.confidence_id,
            "decision_binding": self.decision_binding,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "inputs": dict(sorted(self.inputs_summary.items(), key=lambda kv: kv[0])),
            "limitations": [lim.to_dict() for lim in self.limitations],
            "overall_label": self.overall_label,
            "overall_reason": self.overall_reason,
            "policy_content_hash": self.policy_content_hash,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
        }


def compute_confidence_id(
    *,
    run_id: str,
    dataset_id: str,
    dataset_content_hash: str,
    policy_version: str,
    policy_content_hash: str,
    robustness_run_ids: tuple[str, ...] = (),
    gate_run_id: str | None = None,
) -> str:
    payload = {
        "dataset_content_hash": dataset_content_hash,
        "dataset_id": dataset_id,
        "gate_run_id": gate_run_id,
        "policy_content_hash": policy_content_hash,
        "policy_version": policy_version,
        "robustness_run_ids": sorted(robustness_run_ids),
        "run_id": run_id,
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"conf_{digest}"


def _floors_by_name(policy: ConfidencePolicy) -> dict[str, ConfidenceDimensionFloors]:
    return {d.name: d for d in policy.dimensions}


def _dim(
    floors: ConfidenceDimensionFloors,
    *,
    label: ConfidenceLabel,
    measured: Decimal | int | None,
    reason: str,
    raw: dict[str, Any],
) -> DimensionResult:
    measured_value = None if measured is None else format(Decimal(str(measured)), "f")
    return DimensionResult(
        name=floors.name,
        label=label,
        required=floors.required,
        measured_value=measured_value,
        reason=reason,
        raw_inputs=raw,
    )


def _evaluate_dimensions(
    inputs: ConfidenceEvidenceInputs,
    policy: ConfidencePolicy,
) -> tuple[DimensionResult, ...]:
    floors = _floors_by_name(policy)
    results: list[DimensionResult] = []

    # trade_sample (required)
    ts = floors["trade_sample"]
    if inputs.run_status != "complete":
        results.append(
            _dim(
                ts,
                label="NOT_AVAILABLE",
                measured=inputs.closed_trades,
                reason=f"run_status={inputs.run_status!r}; required complete",
                raw={"closed_trades": inputs.closed_trades, "run_status": inputs.run_status},
            )
        )
    elif inputs.closed_trades is None:
        results.append(
            _dim(
                ts,
                label="NOT_AVAILABLE",
                measured=None,
                reason="closed_trades missing from evidence (never coerce to 0)",
                raw={"closed_trades": None},
            )
        )
    else:
        label = label_from_count(inputs.closed_trades, ts)
        results.append(
            _dim(
                ts,
                label=label,
                measured=inputs.closed_trades,
                reason=f"closed_trades={inputs.closed_trades} → {label}",
                raw={"closed_trades": inputs.closed_trades},
            )
        )

    # time_coverage (optional)
    tc = floors["time_coverage"]
    if inputs.equity_periods is None:
        results.append(
            _dim(
                tc,
                label="NOT_AVAILABLE",
                measured=None,
                reason="equity_periods missing",
                raw={"equity_periods": None},
            )
        )
    else:
        label = label_from_count(inputs.equity_periods, tc)
        results.append(
            _dim(
                tc,
                label=label,
                measured=inputs.equity_periods,
                reason=f"equity_periods={inputs.equity_periods} → {label}",
                raw={"equity_periods": inputs.equity_periods},
            )
        )

    # oos_folds (optional)
    oos = floors["oos_folds"]
    if inputs.walk_forward_folds_complete is None:
        results.append(
            _dim(
                oos,
                label="NOT_AVAILABLE",
                measured=None,
                reason="walk-forward robustness evidence not supplied",
                raw={
                    "walk_forward_fold_pass_ratio": (
                        None
                        if inputs.walk_forward_fold_pass_ratio is None
                        else format(inputs.walk_forward_fold_pass_ratio, "f")
                    ),
                    "walk_forward_folds_complete": None,
                },
            )
        )
    else:
        label = label_from_count(inputs.walk_forward_folds_complete, oos)
        # Cap when fold pass ratio is present and weak.
        if (
            inputs.walk_forward_fold_pass_ratio is not None
            and inputs.walk_forward_fold_pass_ratio < Decimal("0.5")
            and label in {"MEDIUM", "HIGH"}
        ):
            label = "LOW"
        results.append(
            _dim(
                oos,
                label=label,
                measured=inputs.walk_forward_folds_complete,
                reason=(
                    f"walk_forward_folds_complete={inputs.walk_forward_folds_complete} → {label}"
                ),
                raw={
                    "walk_forward_fold_pass_ratio": (
                        None
                        if inputs.walk_forward_fold_pass_ratio is None
                        else format(inputs.walk_forward_fold_pass_ratio, "f")
                    ),
                    "walk_forward_folds_complete": inputs.walk_forward_folds_complete,
                },
            )
        )

    # parameter_plateau (optional)
    pp = floors["parameter_plateau"]
    if inputs.parameter_neighbors_complete is None:
        results.append(
            _dim(
                pp,
                label="NOT_AVAILABLE",
                measured=None,
                reason="parameter-stability robustness evidence not supplied",
                raw={
                    "parameter_neighbor_pass_ratio": (
                        None
                        if inputs.parameter_neighbor_pass_ratio is None
                        else format(inputs.parameter_neighbor_pass_ratio, "f")
                    ),
                    "parameter_neighbors_complete": None,
                },
            )
        )
    else:
        label = label_from_count(inputs.parameter_neighbors_complete, pp)
        if (
            inputs.parameter_neighbor_pass_ratio is not None
            and inputs.parameter_neighbor_pass_ratio < Decimal("0.5")
            and label in {"MEDIUM", "HIGH"}
        ):
            label = "LOW"
        results.append(
            _dim(
                pp,
                label=label,
                measured=inputs.parameter_neighbors_complete,
                reason=(
                    f"parameter_neighbors_complete={inputs.parameter_neighbors_complete} → {label}"
                ),
                raw={
                    "parameter_neighbor_pass_ratio": (
                        None
                        if inputs.parameter_neighbor_pass_ratio is None
                        else format(inputs.parameter_neighbor_pass_ratio, "f")
                    ),
                    "parameter_neighbors_complete": inputs.parameter_neighbors_complete,
                },
            )
        )

    # bootstrap_uncertainty (optional; serial-dependence proxy)
    boot = floors["bootstrap_uncertainty"]
    if not inputs.bootstrap_assessed or inputs.bootstrap_series_length is None:
        results.append(
            _dim(
                boot,
                label="NOT_AVAILABLE",
                measured=None,
                reason="bootstrap serial-dependence assessment not available",
                raw={
                    "bootstrap_assessed": inputs.bootstrap_assessed,
                    "bootstrap_block_length": inputs.bootstrap_block_length,
                    "bootstrap_series_length": inputs.bootstrap_series_length,
                },
            )
        )
    else:
        # Effective length after requiring block_length < series (else INSUFFICIENT).
        series = inputs.bootstrap_series_length
        block = inputs.bootstrap_block_length
        if block is not None and block >= series:
            label = "INSUFFICIENT"
            reason = (
                f"bootstrap block_length={block} >= series_length={series} "
                "(cannot assess serial dependence)"
            )
        else:
            label = label_from_count(series, boot)
            reason = f"bootstrap_series_length={series} → {label}"
        results.append(
            _dim(
                boot,
                label=label,
                measured=series,
                reason=reason,
                raw={
                    "bootstrap_assessed": True,
                    "bootstrap_block_length": block,
                    "bootstrap_series_length": series,
                },
            )
        )

    # regime_coverage (optional)
    rc = floors["regime_coverage"]
    if inputs.regime_coverage_ratio is None:
        results.append(
            _dim(
                rc,
                label="NOT_AVAILABLE",
                measured=None,
                reason="regime coverage ratio not supplied",
                raw={
                    "regime_coverage_ratio": None,
                    "regime_evidence_status": inputs.regime_evidence_status,
                },
            )
        )
    else:
        label = label_from_count(inputs.regime_coverage_ratio, rc)
        if inputs.regime_evidence_status == "INCONCLUSIVE" and label in {
            "MEDIUM",
            "HIGH",
        }:
            label = "LOW"
        results.append(
            _dim(
                rc,
                label=label,
                measured=inputs.regime_coverage_ratio,
                reason=(
                    f"regime_coverage_ratio={inputs.regime_coverage_ratio} → {label}"
                ),
                raw={
                    "regime_coverage_ratio": format(inputs.regime_coverage_ratio, "f"),
                    "regime_evidence_status": inputs.regime_evidence_status,
                },
            )
        )

    return tuple(results)


def _aggregate(
    dimensions: tuple[DimensionResult, ...],
    *,
    integrity_status: str | None,
) -> tuple[ConfidenceLabel, str]:
    if integrity_status == "INVALID":
        return (
            "NOT_AVAILABLE",
            "gate_integrity_status=INVALID blocks trusted confidence (fail closed)",
        )

    required_missing = [d for d in dimensions if d.required and d.label == "NOT_AVAILABLE"]
    if required_missing:
        names = ", ".join(d.name for d in required_missing)
        return (
            "NOT_AVAILABLE",
            f"required dimension(s) NOT_AVAILABLE: {names}",
        )

    present = [d for d in dimensions if d.label != "NOT_AVAILABLE"]
    if not present:
        return ("NOT_AVAILABLE", "no measurable confidence dimensions available")

    overall: ConfidenceLabel = present[0].label
    for dim in present[1:]:
        overall = worse_label(overall, dim.label)
    return (
        overall,
        f"min_present over {[d.name for d in present]} → {overall}",
    )


def evaluate_confidence(
    inputs: ConfidenceEvidenceInputs,
    *,
    policy_version: str = "1.0",
) -> ConfidenceResult:
    try:
        policy = get_confidence_policy(policy_version)
    except ConfidencePolicyError as exc:
        raise ConfidenceEvaluationError(str(exc)) from exc

    policy_hash = compute_confidence_policy_content_hash(policy)
    dimensions = _evaluate_dimensions(inputs, policy)
    overall_label, overall_reason = _aggregate(
        dimensions, integrity_status=inputs.gate_integrity_status
    )
    limitations = build_limitations(inputs)
    confidence_id = compute_confidence_id(
        run_id=inputs.run_id,
        dataset_id=inputs.dataset_id,
        dataset_content_hash=inputs.dataset_content_hash,
        policy_version=policy.version,
        policy_content_hash=policy_hash,
        robustness_run_ids=inputs.robustness_run_ids,
        gate_run_id=inputs.gate_run_id,
    )
    inputs_summary = {
        "bootstrap_assessed": inputs.bootstrap_assessed,
        "bootstrap_block_length": inputs.bootstrap_block_length,
        "bootstrap_series_length": inputs.bootstrap_series_length,
        "closed_trades": inputs.closed_trades,
        "dataset_content_hash": inputs.dataset_content_hash,
        "dataset_id": inputs.dataset_id,
        "equity_periods": inputs.equity_periods,
        "experiment_id": inputs.experiment_id,
        "gate_integrity_status": inputs.gate_integrity_status,
        "gate_run_id": inputs.gate_run_id,
        "parameter_neighbor_pass_ratio": (
            None
            if inputs.parameter_neighbor_pass_ratio is None
            else format(inputs.parameter_neighbor_pass_ratio, "f")
        ),
        "parameter_neighbors_complete": inputs.parameter_neighbors_complete,
        "regime_coverage_ratio": (
            None
            if inputs.regime_coverage_ratio is None
            else format(inputs.regime_coverage_ratio, "f")
        ),
        "regime_evidence_status": inputs.regime_evidence_status,
        "robustness_run_ids": list(inputs.robustness_run_ids),
        "run_id": inputs.run_id,
        "run_status": inputs.run_status,
        "walk_forward_fold_pass_ratio": (
            None
            if inputs.walk_forward_fold_pass_ratio is None
            else format(inputs.walk_forward_fold_pass_ratio, "f")
        ),
        "walk_forward_folds_complete": inputs.walk_forward_folds_complete,
    }
    return ConfidenceResult(
        confidence_id=confidence_id,
        schema_version=CONFIDENCE_PROFILE_SCHEMA_VERSION,
        policy_version=policy.version,
        policy_content_hash=policy_hash,
        overall_label=overall_label,
        overall_reason=overall_reason,
        dimensions=dimensions,
        limitations=limitations,
        inputs_summary=inputs_summary,
        decision_binding=False,
        auto_promotion=False,
    )
