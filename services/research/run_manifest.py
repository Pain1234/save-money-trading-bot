"""Immutable RunManifest (Issue #142 / P4-02).

After finalize, the RunManifest must never be mutated. Invalidation is recorded
via registry and/or append-only sidecar only (see #145).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from research.experiment_spec import ExperimentSpec
from research.identity import (
    IDENTITY_HASH_ALGORITHM,
    RunIdentityInputs,
    compute_experiment_id,
    compute_run_id,
)

RUN_MANIFEST_SCHEMA_VERSION = "1.0"


class RunManifest(BaseModel):
    """Machine-readable, immutable identity record for a research run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=RUN_MANIFEST_SCHEMA_VERSION)
    experiment_id: str
    run_id: str
    attempt_id: str
    git_commit: str
    dataset_id: str
    dataset_content_hash: str
    strategy_version: str
    cost_model_version: str
    metrics_schema_version: str
    environment_fingerprint: str
    identity_hash_algorithm: str = Field(default=IDENTITY_HASH_ALGORITHM)
    # Metadata only — never used as an identity source.
    created_at_utc: datetime
    status: Literal["complete", "failed", "incomplete"] = "incomplete"

    @field_validator("created_at_utc", mode="after")
    @classmethod
    def _utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            msg = "created_at_utc must be timezone-aware"
            raise ValueError(msg)
        return value.astimezone(UTC)

    @field_validator("schema_version")
    @classmethod
    def _supported(cls, value: str) -> str:
        if value != RUN_MANIFEST_SCHEMA_VERSION:
            msg = (
                f"unsupported run manifest schema_version {value!r}; "
                f"expected {RUN_MANIFEST_SCHEMA_VERSION!r}"
            )
            raise ValueError(msg)
        return value


def build_run_manifest(
    spec: ExperimentSpec,
    *,
    inputs: RunIdentityInputs,
    attempt_id: str,
    created_at_utc: datetime | None = None,
    status: Literal["complete", "failed", "incomplete"] = "incomplete",
) -> RunManifest:
    """Build a RunManifest from Spec + identity inputs."""
    experiment_id = compute_experiment_id(spec)
    run_id = compute_run_id(spec, inputs)
    return RunManifest(
        experiment_id=experiment_id,
        run_id=run_id,
        attempt_id=attempt_id,
        git_commit=inputs.git_commit,
        dataset_id=spec.dataset_manifest_ref.dataset_id,
        dataset_content_hash=inputs.dataset_content_hash,
        strategy_version=inputs.strategy_version,
        cost_model_version=inputs.cost_model_version,
        metrics_schema_version=inputs.metrics_schema_version,
        environment_fingerprint=inputs.environment_fingerprint,
        created_at_utc=created_at_utc or datetime.now(UTC),
        status=status,
    )


def run_manifest_to_canonical_dict(manifest: RunManifest) -> dict[str, Any]:
    """JSON-compatible dict with ISO timestamps."""
    data = manifest.model_dump(mode="python")
    created = data["created_at_utc"]
    assert isinstance(created, datetime)
    data["created_at_utc"] = created.astimezone(UTC).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    return data


def dumps_run_manifest(manifest: RunManifest) -> bytes:
    """Deterministic UTF-8 JSON bytes for storage (excluding volatile compare)."""
    payload = json.dumps(
        run_manifest_to_canonical_dict(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return payload.encode("utf-8")


def save_run_manifest(manifest: RunManifest, path: str | Path) -> None:
    """Write run_manifest.json. Refuses to overwrite an existing file."""
    file_path = Path(path)
    if file_path.exists():
        msg = f"refusing to overwrite immutable RunManifest at {file_path}"
        raise FileExistsError(msg)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(dumps_run_manifest(manifest) + b"\n")


def load_run_manifest(path: str | Path) -> RunManifest:
    """Load and validate a RunManifest JSON document."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = "RunManifest root must be a mapping/object"
        raise ValueError(msg)
    return RunManifest.model_validate(raw)


def semantic_manifest_payload(manifest: RunManifest) -> dict[str, Any]:
    """Manifest fields used for CI double-run semantic compares.

    Excludes attempt_id and created_at_utc (intentional non-determinism).
    """
    data = run_manifest_to_canonical_dict(manifest)
    data.pop("attempt_id", None)
    data.pop("created_at_utc", None)
    return data
