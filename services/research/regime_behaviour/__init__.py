"""P4.9 deterministic regime behaviour + transition-risk labels (#289)."""

from __future__ import annotations

from research.regime_behaviour.artifacts import (
    BehaviourArtifactError,
    verify_behaviour_profile_seal,
    write_behaviour_profile_artifact,
)
from research.regime_behaviour.evaluator import (
    BEHAVIOUR_PROFILE_FILENAME,
    BEHAVIOUR_PROFILE_SCHEMA_VERSION,
    BehaviourProfileError,
    BehaviourProfileResult,
    compute_behaviour_id,
    evaluate_behaviour_profile,
    evaluate_behaviour_profile_from_run_dir,
)
from research.regime_behaviour.labels import (
    BEHAVIOUR_LABELS,
    derive_regime_labels,
    pick_main_strength,
    pick_main_weakness,
)
from research.regime_behaviour.policy import (
    BehaviourPolicy,
    BehaviourPolicyError,
    compute_policy_content_hash,
    get_behaviour_policy,
    verify_behaviour_policy_content_hash,
)
from research.regime_behaviour.transitions import build_transition_risk_profile

__all__ = [
    "BEHAVIOUR_LABELS",
    "BEHAVIOUR_PROFILE_FILENAME",
    "BEHAVIOUR_PROFILE_SCHEMA_VERSION",
    "BehaviourArtifactError",
    "BehaviourPolicy",
    "BehaviourPolicyError",
    "BehaviourProfileError",
    "BehaviourProfileResult",
    "build_transition_risk_profile",
    "compute_behaviour_id",
    "compute_policy_content_hash",
    "derive_regime_labels",
    "evaluate_behaviour_profile",
    "evaluate_behaviour_profile_from_run_dir",
    "get_behaviour_policy",
    "pick_main_strength",
    "pick_main_weakness",
    "verify_behaviour_policy_content_hash",
    "verify_behaviour_profile_seal",
    "write_behaviour_profile_artifact",
]
