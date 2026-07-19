"""P4.9 parameter-area / plateau classification (#290)."""

from __future__ import annotations

from research.parameter_area.artifacts import (
    ParameterAreaArtifactError,
    verify_parameter_area_seal,
    write_parameter_area_artifact,
)
from research.parameter_area.evaluator import (
    PARAMETER_AREA_FILENAME,
    PARAMETER_AREA_SCHEMA_VERSION,
    NeighborObservation,
    ParameterAreaError,
    ParameterAreaResult,
    compute_parameter_area_id,
    evaluate_parameter_area,
    evaluate_parameter_area_from_robustness,
    is_neighbor_stable,
    observations_from_manifest,
    observations_from_sealed_manifest,
    reconstruct_oat_variants,
)
from research.parameter_area.policy import (
    PARAMETER_AREA_LABELS,
    ParameterAreaPolicy,
    ParameterAreaPolicyError,
    compute_policy_content_hash,
    get_parameter_area_policy,
    verify_parameter_area_policy_content_hash,
)

__all__ = [
    "PARAMETER_AREA_FILENAME",
    "PARAMETER_AREA_LABELS",
    "PARAMETER_AREA_SCHEMA_VERSION",
    "NeighborObservation",
    "ParameterAreaArtifactError",
    "ParameterAreaError",
    "ParameterAreaPolicy",
    "ParameterAreaPolicyError",
    "ParameterAreaResult",
    "compute_parameter_area_id",
    "compute_policy_content_hash",
    "evaluate_parameter_area",
    "evaluate_parameter_area_from_robustness",
    "get_parameter_area_policy",
    "is_neighbor_stable",
    "observations_from_manifest",
    "observations_from_sealed_manifest",
    "reconstruct_oat_variants",
    "verify_parameter_area_policy_content_hash",
    "verify_parameter_area_seal",
    "write_parameter_area_artifact",
]
