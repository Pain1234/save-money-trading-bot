"""P4.9 evidence confidence profile (#288).

Layer-3 scorecard confidence is derived from measurable research evidence only.
It is separate from regime quality scores (#287) and does not auto-promote.
"""

from __future__ import annotations

from research.confidence.artifacts import (
    ConfidenceArtifactError,
    verify_confidence_profile_seal,
    write_confidence_profile_artifact,
)
from research.confidence.evaluator import (
    CONFIDENCE_PROFILE_FILENAME,
    CONFIDENCE_PROFILE_SCHEMA_VERSION,
    ConfidenceEvaluationError,
    ConfidenceResult,
    DimensionResult,
    compute_confidence_id,
    evaluate_confidence,
)
from research.confidence.inputs import (
    ConfidenceEvidenceInputs,
    ConfidenceLimitation,
    build_limitations,
)
from research.confidence.policy import (
    CONFIDENCE_POLICY_1_0_CONTENT_HASH,
    ConfidenceDimensionFloors,
    ConfidenceLabel,
    ConfidencePolicy,
    ConfidencePolicyError,
    compute_confidence_policy_content_hash,
    get_confidence_policy,
    list_confidence_policy_versions,
    verify_confidence_policy_content_hash,
)

__all__ = [
    "CONFIDENCE_POLICY_1_0_CONTENT_HASH",
    "CONFIDENCE_PROFILE_FILENAME",
    "CONFIDENCE_PROFILE_SCHEMA_VERSION",
    "ConfidenceArtifactError",
    "ConfidenceDimensionFloors",
    "ConfidenceEvaluationError",
    "ConfidenceEvidenceInputs",
    "ConfidenceLabel",
    "ConfidenceLimitation",
    "ConfidencePolicy",
    "ConfidencePolicyError",
    "ConfidenceResult",
    "DimensionResult",
    "build_limitations",
    "compute_confidence_id",
    "compute_confidence_policy_content_hash",
    "evaluate_confidence",
    "get_confidence_policy",
    "list_confidence_policy_versions",
    "verify_confidence_policy_content_hash",
    "verify_confidence_profile_seal",
    "write_confidence_profile_artifact",
]
