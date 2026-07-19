"""Evaluate ``parameter_area.json`` from #247 parameter-stability evidence (#290)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from research.parameter_area.classify import classify_parameter_area
from research.parameter_area.graph import build_axis_points, measure_contiguous_regions
from research.parameter_area.policy import (
    ParameterAreaPolicyError,
    compute_policy_content_hash,
    get_parameter_area_policy,
)
from research.parameter_stability import symmetric_neighborhood
from research.robustness import (
    load_robustness_manifest,
    verify_robustness_manifest_seal,
)

PARAMETER_AREA_SCHEMA_VERSION = "1.0"
PARAMETER_AREA_FILENAME = "parameter_area.json"


class ParameterAreaError(Exception):
    """Missing inputs, pin mismatch, or integrity failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _optional_dec(value: object | None) -> Decimal | None:
    if value is None or value == "NOT_AVAILABLE":
        return None
    return Decimal(str(value))


def _param_variant_label(base: Mapping[str, Any], variant: Mapping[str, Any]) -> str:
    changed = [
        f"{key}={variant[key]}"
        for key in sorted(variant)
        if key != "strategy_id" and variant.get(key) != base.get(key)
    ]
    return "baseline" if not changed else ",".join(changed)


def reconstruct_oat_variants(
    frozen_parameters: Mapping[str, Any],
    *,
    int_deltas: dict[str, tuple[int, ...]] | None = None,
    decimal_relative_steps: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """Mirror #247 child ordering: frozen first, then OAT neighbors."""
    variants = symmetric_neighborhood(
        dict(frozen_parameters),
        int_deltas=int_deltas,
        decimal_relative_steps=decimal_relative_steps,
    )
    rows: list[dict[str, Any]] = []
    base = dict(frozen_parameters)
    for index, variant in enumerate(variants):
        child_id = "frozen" if index == 0 else f"neighbor_{index:02d}"
        rows.append(
            {
                "child_id": child_id,
                "label": _param_variant_label(base, variant),
                "parameters": dict(variant),
            }
        )
    return rows


def compute_evidence_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(dict(payload))).hexdigest()


def compute_parameter_area_id(
    *,
    robustness_id: str,
    policy_version: str,
    policy_content_hash: str,
    evidence_hash: str,
) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "evidence_hash": evidence_hash,
                "policy_content_hash": policy_content_hash,
                "policy_version": policy_version,
                "robustness_id": robustness_id,
            }
        )
    ).hexdigest()
    return f"pa_{digest}"


@dataclass(frozen=True)
class NeighborObservation:
    child_id: str
    label: str
    parameters: dict[str, Any]
    status: str
    net_pnl: str | None
    total_costs: str | None
    gate_pass: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "gate_pass": self.gate_pass,
            "label": self.label,
            "net_pnl": self.net_pnl,
            "parameters": dict(sorted(self.parameters.items(), key=lambda kv: kv[0])),
            "status": self.status,
            "total_costs": self.total_costs,
        }


@dataclass(frozen=True)
class ParameterAreaResult:
    artifact: dict[str, Any]
    parameter_area_id: str
    classification: str


def is_neighbor_stable(
    *,
    status: str,
    net_pnl: Decimal | None,
    total_costs: Decimal | None,
    gate_pass: bool | None,
    require_gate: bool,
    policy_min_net: Decimal,
    policy_max_cost_ratio: Decimal,
) -> tuple[bool, str]:
    """Stable requires complete + PnL floor + cost bound (+ gate when required)."""
    if status != "complete":
        return False, "not_complete"
    if net_pnl is None:
        return False, "missing_net_pnl"
    if net_pnl < policy_min_net:
        return False, "net_pnl_below_floor"
    if total_costs is None:
        return False, "missing_costs"
    denom = max(abs(net_pnl), Decimal("1"))
    if total_costs / denom > policy_max_cost_ratio:
        return False, "cost_ratio_exceeded"
    if require_gate:
        if gate_pass is None:
            return False, "missing_gate_pass"
        if gate_pass is not True:
            return False, "gate_fail"
    return True, "stable"


def evaluate_parameter_area(
    *,
    robustness_id: str,
    frozen_parameters: Mapping[str, Any],
    observations: Sequence[NeighborObservation],
    neighborhood_config: Mapping[str, Any] | None = None,
    policy_version: str = "1.0",
    require_gate_for_stable: bool = False,
) -> ParameterAreaResult:
    """Classify plateau / local stability from sealed neighbor observations.

    Does not select or mutate parameters. ``decision_binding`` / ``auto_promotion``
    are always false.
    """
    policy = get_parameter_area_policy(policy_version)
    policy_hash = compute_policy_content_hash(policy)
    if not robustness_id:
        raise ParameterAreaError("robustness_id required")
    if not frozen_parameters:
        raise ParameterAreaError("frozen_parameters required")

    frozen_rows = [o for o in observations if o.child_id == "frozen"]
    if len(frozen_rows) != 1:
        raise ParameterAreaError("exactly one frozen observation required")
    frozen = frozen_rows[0]
    neighbors = [o for o in observations if o.child_id != "frozen"]

    min_net = Decimal(policy.min_net_pnl)
    max_cost = Decimal(policy.max_cost_ratio)

    def _eval(obs: NeighborObservation) -> dict[str, Any]:
        net = _optional_dec(obs.net_pnl)
        costs = _optional_dec(obs.total_costs)
        stable, reason = is_neighbor_stable(
            status=obs.status,
            net_pnl=net,
            total_costs=costs,
            gate_pass=obs.gate_pass,
            require_gate=require_gate_for_stable,
            policy_min_net=min_net,
            policy_max_cost_ratio=max_cost,
        )
        return {
            "child_id": obs.child_id,
            "label": obs.label,
            "parameters": dict(obs.parameters),
            "status": obs.status,
            "net_pnl": obs.net_pnl if obs.net_pnl is not None else "NOT_AVAILABLE",
            "total_costs": (
                obs.total_costs if obs.total_costs is not None else "NOT_AVAILABLE"
            ),
            "gate_pass": obs.gate_pass,
            "stable": stable,
            "stable_reason": reason,
            "positive": bool(net is not None and net >= min_net),
        }

    frozen_eval = _eval(frozen)
    neighbor_evals = [_eval(n) for n in neighbors]

    complete_neighbors = [n for n in neighbor_evals if n["status"] == "complete"]
    n_complete = len(complete_neighbors)
    stable_neighbors = [n for n in complete_neighbors if n["stable"]]
    positive_neighbors = [n for n in complete_neighbors if n["positive"]]

    gate_known = [n for n in complete_neighbors if n["gate_pass"] is not None]
    gates_available = len(gate_known) == n_complete and n_complete > 0
    gate_pass_share: Decimal | None
    if gates_available:
        gate_pass_share = Decimal(sum(1 for n in gate_known if n["gate_pass"])) / Decimal(
            n_complete
        )
    else:
        gate_pass_share = None

    stable_share = (
        Decimal(len(stable_neighbors)) / Decimal(n_complete)
        if n_complete
        else Decimal("0")
    )
    positive_share = (
        Decimal(len(positive_neighbors)) / Decimal(n_complete)
        if n_complete
        else Decimal("0")
    )

    nets = [_optional_dec(n["net_pnl"]) for n in complete_neighbors]
    nets_present = [n for n in nets if n is not None]
    median_net: str | None
    dispersion: str | None
    if nets_present:
        ordered = sorted(nets_present)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            median_net = format(ordered[mid], "f")
        else:
            median_net = format((ordered[mid - 1] + ordered[mid]) / 2, "f")
        dispersion = format(ordered[-1] - ordered[0], "f")
    else:
        median_net = "NOT_AVAILABLE"
        dispersion = "NOT_AVAILABLE"

    frozen_net = _optional_dec(frozen_eval["net_pnl"])
    steepest: Decimal | None = None
    if frozen_net is not None:
        for n in nets_present:
            drop = frozen_net - n
            if steepest is None or drop > steepest:
                steepest = drop
    steepest_drop = format(steepest, "f") if steepest is not None else "NOT_AVAILABLE"

    by_axis = build_axis_points(
        frozen_child_id="frozen",
        frozen_parameters=frozen_parameters,
        frozen_stable=bool(frozen_eval["stable"]),
        neighbors=neighbor_evals,
    )
    region = measure_contiguous_regions(by_axis)
    plateau_size = int(region["plateau_size"])

    classification, reason = classify_parameter_area(
        policy=policy,
        n_complete_neighbors=n_complete,
        stable_share=stable_share,
        gate_pass_share=gate_pass_share,
        gates_available=gates_available,
        plateau_size=plateau_size,
        frozen_stable=bool(frozen_eval["stable"]),
        any_stable_neighbor=bool(stable_neighbors),
        steepest_drop=steepest,
    )
    isolated = classification == "ISOLATED_PEAK"

    evidence_payload = {
        "frozen": frozen_eval,
        "neighbors": neighbor_evals,
        "neighborhood_config": dict(neighborhood_config or {}),
        "require_gate_for_stable": require_gate_for_stable,
    }
    evidence_hash = compute_evidence_hash(evidence_payload)
    parameter_area_id = compute_parameter_area_id(
        robustness_id=robustness_id,
        policy_version=policy.version,
        policy_content_hash=policy_hash,
        evidence_hash=evidence_hash,
    )

    artifact: dict[str, Any] = {
        "schema_version": PARAMETER_AREA_SCHEMA_VERSION,
        "parameter_area_id": parameter_area_id,
        "robustness_id": robustness_id,
        "policy_version": policy.version,
        "policy_content_hash": policy_hash,
        "evidence_hash": evidence_hash,
        "neighborhood": {
            "version_note": "reuse #247 parameter_stability OAT neighborhood",
            "contiguity_rule": policy.contiguity_rule,
            "config": dict(neighborhood_config or {}),
            "require_gate_for_stable": require_gate_for_stable,
        },
        "frozen_point": {
            "child_id": frozen.child_id,
            "label": frozen.label,
            "parameters": dict(
                sorted(dict(frozen_parameters).items(), key=lambda kv: kv[0])
            ),
            "status": frozen_eval["status"],
            "net_pnl": frozen_eval["net_pnl"],
            "total_costs": frozen_eval["total_costs"],
            "gate_pass": frozen_eval["gate_pass"],
            "stable": frozen_eval["stable"],
            "unchanged": True,
            "auto_selected": False,
        },
        "neighbors": neighbor_evals,
        "stats": {
            "n_neighbors": len(neighbors),
            "n_complete_neighbors": n_complete,
            "share_positive": format(positive_share, "f"),
            "share_stable": format(stable_share, "f"),
            "share_gate_pass": (
                format(gate_pass_share, "f")
                if gate_pass_share is not None
                else "NOT_AVAILABLE"
            ),
            "gates_available": gates_available,
            "median_neighbor_net_pnl": median_net,
            "dispersion_neighbor_net_pnl": dispersion,
            "steepest_local_drop": steepest_drop,
        },
        "plateau": {
            "size": plateau_size,
            "contiguous_region": region,
            "isolated_optimum": isolated,
        },
        "classification": classification,
        "classification_reason": reason,
        "decision_binding": False,
        "auto_promotion": False,
        "auto_parameter_selection": False,
        "oos_holdout_used": False,
    }
    return ParameterAreaResult(
        artifact=artifact,
        parameter_area_id=parameter_area_id,
        classification=classification,
    )


def observations_from_manifest(
    manifest: Mapping[str, Any],
    *,
    frozen_parameters: Mapping[str, Any],
    costs_by_child: Mapping[str, str | None] | None = None,
    gate_pass_by_child: Mapping[str, bool | None] | None = None,
) -> tuple[list[NeighborObservation], dict[str, Any]]:
    """Build observations from a parameter_stability robustness manifest."""
    if manifest.get("test_type") != "parameter_stability":
        raise ParameterAreaError(
            f"expected test_type=parameter_stability, got {manifest.get('test_type')!r}"
        )
    config = dict(manifest.get("config") or {})
    int_deltas = config.get("int_deltas")
    decimal_steps = config.get("decimal_relative_steps")
    # Config may store lists; normalize to tuples for symmetric_neighborhood.
    int_norm: dict[str, tuple[int, ...]] | None = None
    if isinstance(int_deltas, dict):
        int_norm = {k: tuple(int(x) for x in v) for k, v in int_deltas.items()}
    dec_norm: dict[str, tuple[str, ...]] | None = None
    if isinstance(decimal_steps, dict):
        dec_norm = {k: tuple(str(x) for x in v) for k, v in decimal_steps.items()}

    variants = reconstruct_oat_variants(
        frozen_parameters,
        int_deltas=int_norm,
        decimal_relative_steps=dec_norm,
    )
    by_id = {row["child_id"]: row for row in variants}
    costs = costs_by_child or {}
    gates = gate_pass_by_child or {}

    observations: list[NeighborObservation] = []
    for child in manifest.get("children") or []:
        if not isinstance(child, dict):
            continue
        child_id = str(child.get("child_id") or "")
        if child_id not in by_id:
            raise ParameterAreaError(
                f"manifest child {child_id!r} not in reconstructed OAT neighborhood"
            )
        meta = by_id[child_id]
        observations.append(
            NeighborObservation(
                child_id=child_id,
                label=str(child.get("label") or meta["label"]),
                parameters=dict(meta["parameters"]),
                status=str(child.get("status") or ""),
                net_pnl=child.get("net_pnl"),
                total_costs=costs.get(child_id),
                gate_pass=gates.get(child_id),
            )
        )
    return observations, config


def evaluate_parameter_area_from_robustness(
    root: Path,
    robustness_id: str,
    *,
    frozen_parameters: Mapping[str, Any],
    costs_by_child: Mapping[str, str | None] | None = None,
    gate_pass_by_child: Mapping[str, bool | None] | None = None,
    policy_version: str = "1.0",
    require_gate_for_stable: bool = False,
    require_seal: bool = True,
) -> ParameterAreaResult:
    """Load sealed #247 robustness manifest and classify parameter area."""
    if require_seal:
        try:
            verify_robustness_manifest_seal(root, robustness_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ParameterAreaError(f"robustness seal verify failed: {exc}") from exc
    manifest = load_robustness_manifest(root, robustness_id)
    if manifest is None:
        raise ParameterAreaError(f"missing robustness manifest for {robustness_id}")
    observations, config = observations_from_manifest(
        manifest,
        frozen_parameters=frozen_parameters,
        costs_by_child=costs_by_child,
        gate_pass_by_child=gate_pass_by_child,
    )
    return evaluate_parameter_area(
        robustness_id=str(manifest.get("robustness_id") or robustness_id),
        frozen_parameters=frozen_parameters,
        observations=observations,
        neighborhood_config=config,
        policy_version=policy_version,
        require_gate_for_stable=require_gate_for_stable,
    )


__all__ = [
    "PARAMETER_AREA_FILENAME",
    "PARAMETER_AREA_SCHEMA_VERSION",
    "NeighborObservation",
    "ParameterAreaError",
    "ParameterAreaPolicyError",
    "ParameterAreaResult",
    "compute_parameter_area_id",
    "evaluate_parameter_area",
    "evaluate_parameter_area_from_robustness",
    "is_neighbor_stable",
    "observations_from_manifest",
    "reconstruct_oat_variants",
]
