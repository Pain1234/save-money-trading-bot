"""Deterministic experiment/run identity (Issue #142 / P4-02).

Identity rules (binding):
- experiment_id: hash of semantic ExperimentSpec fields only (owner/notes excluded)
- run_id: hash of experiment identity inputs + code commit + dataset + model/env versions
- attempt_id: opaque id for a physical execution attempt of the same run_id
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from research.experiment_spec import ExperimentSpec, to_canonical_dict

# Non-semantic metadata: must not affect experiment_id.
_NON_SEMANTIC_SPEC_KEYS: frozenset[str] = frozenset({"owner", "notes"})

IDENTITY_HASH_ALGORITHM = "sha256"
EXPERIMENT_ID_PREFIX = "exp_"
RUN_ID_PREFIX = "run_"
ATTEMPT_ID_PREFIX = "att_"


def semantic_spec_dict(spec: ExperimentSpec) -> dict[str, Any]:
    """Canonical dict of semantic Spec fields only (excludes owner/notes)."""
    full = to_canonical_dict(spec)
    return {k: v for k, v in full.items() if k not in _NON_SEMANTIC_SPEC_KEYS}


def _stable_json_bytes(payload: Mapping[str, Any]) -> bytes:
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return text.encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_experiment_id(spec: ExperimentSpec) -> str:
    """Deterministic experiment_id from semantic Spec fields only."""
    digest = _sha256_hex(_stable_json_bytes(semantic_spec_dict(spec)))
    return f"{EXPERIMENT_ID_PREFIX}{digest}"


@dataclass(frozen=True)
class RunIdentityInputs:
    """Inputs that participate in run_id (besides the semantic Spec)."""

    git_commit: str
    dataset_content_hash: str
    strategy_version: str
    cost_model_version: str
    metrics_schema_version: str
    environment_fingerprint: str

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "cost_model_version": self.cost_model_version,
            "dataset_content_hash": self.dataset_content_hash,
            "environment_fingerprint": self.environment_fingerprint,
            "git_commit": self.git_commit,
            "metrics_schema_version": self.metrics_schema_version,
            "strategy_version": self.strategy_version,
        }


def compute_run_id(spec: ExperimentSpec, inputs: RunIdentityInputs) -> str:
    """Deterministic run_id from Spec semantics + code/dataset/model/env pins."""
    if inputs.dataset_content_hash != spec.dataset_manifest_ref.content_hash:
        msg = (
            "dataset_content_hash must match "
            "spec.dataset_manifest_ref.content_hash"
        )
        raise ValueError(msg)
    if inputs.strategy_version != spec.strategy_version:
        msg = "strategy_version must match spec.strategy_version"
        raise ValueError(msg)
    payload = {
        "experiment": semantic_spec_dict(spec),
        "run_inputs": inputs.to_canonical_dict(),
    }
    digest = _sha256_hex(_stable_json_bytes(payload))
    return f"{RUN_ID_PREFIX}{digest}"


def new_attempt_id() -> str:
    """Allocate a new attempt_id for a physical execution of a run_id."""
    return f"{ATTEMPT_ID_PREFIX}{uuid.uuid4().hex}"


def semantic_artifact_hash(payload: Mapping[str, Any] | bytes | str) -> str:
    """Hash used for CI double-run compares (excludes attempt/timestamps)."""
    if isinstance(payload, bytes):
        return _sha256_hex(payload)
    if isinstance(payload, str):
        return _sha256_hex(payload.encode("utf-8"))
    return _sha256_hex(_stable_json_bytes(payload))
