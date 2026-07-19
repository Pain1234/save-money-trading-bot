"""Scorecard evaluator + append-only persistence (Issue #291 / P4.9).

Aggregates already-produced layer artifacts (regime labels/metrics/behaviour,
confidence, optional parameter area) into a Layer-5 global profile. No second
experiment registry, no re-backtest, no auto-promotion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from research.artifacts import verify_checksums_against
from research.confidence import (
    ConfidenceEvidenceInputs,
    evaluate_confidence,
)
from research.gate_evaluator import (
    GateResultStore,
    _resolve_evaluation_code_commit,
    verify_gate_record_artifact_checksums,
)
from research.registry import ExperimentRegistry, RegistryEntry
from research.run_manifest import load_run_manifest
from research.scorecard_policy import (
    ScorecardPolicy,
    ScorecardPolicyError,
    compute_scorecard_policy_content_hash,
    get_scorecard_policy,
)

SCORECARD_RECORD_SCHEMA_VERSION = "1.0"
ScorecardStatus = Literal["active", "invalidated"]


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ScorecardEvaluationError(Exception):
    """Evidence could not be resolved/bound for scorecard evaluation."""

    def __init__(self, message: str, *, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


@dataclass(frozen=True)
class ScorecardLimitation:
    code: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "status": self.status}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ScorecardLimitation:
        return cls(
            code=str(raw["code"]),
            status=str(raw["status"]),
            detail=str(raw["detail"]),
        )


@dataclass(frozen=True)
class ScorecardRecord:
    """One append-only, immutable scorecard evaluation record."""

    schema_version: str
    scorecard_id: str
    policy_version: str
    policy_content_hash: str
    evaluated_at: str
    run_code_commit: str
    evaluation_code_commit: str
    experiment_id: str
    run_id: str
    gate_run_id: str | None
    robustness_run_ids: tuple[str, ...]
    dataset_id: str
    dataset_content_hash: str
    artifact_checksums: dict[str, str]
    layer_refs: dict[str, Any]
    global_profile: dict[str, Any]
    limitations: tuple[ScorecardLimitation, ...]
    decision_binding: bool = False
    auto_promotion: bool = False
    promotion_action: Literal["none"] = "none"
    status: ScorecardStatus = "active"
    invalidation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_checksums": dict(sorted(self.artifact_checksums.items())),
            "auto_promotion": self.auto_promotion,
            "dataset_content_hash": self.dataset_content_hash,
            "dataset_id": self.dataset_id,
            "decision_binding": self.decision_binding,
            "evaluated_at": self.evaluated_at,
            "evaluation_code_commit": self.evaluation_code_commit,
            "experiment_id": self.experiment_id,
            "gate_run_id": self.gate_run_id,
            "global_profile": self.global_profile,
            "invalidation_reason": self.invalidation_reason,
            "layer_refs": self.layer_refs,
            "limitations": [lim.to_dict() for lim in self.limitations],
            "policy_content_hash": self.policy_content_hash,
            "policy_version": self.policy_version,
            "promotion_action": self.promotion_action,
            "robustness_run_ids": list(self.robustness_run_ids),
            "run_code_commit": self.run_code_commit,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "scorecard_id": self.scorecard_id,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ScorecardRecord:
        return cls(
            schema_version=str(raw["schema_version"]),
            scorecard_id=str(raw["scorecard_id"]),
            policy_version=str(raw["policy_version"]),
            policy_content_hash=str(raw["policy_content_hash"]),
            evaluated_at=str(raw["evaluated_at"]),
            run_code_commit=str(raw["run_code_commit"]),
            evaluation_code_commit=str(raw["evaluation_code_commit"]),
            experiment_id=str(raw["experiment_id"]),
            run_id=str(raw["run_id"]),
            gate_run_id=raw.get("gate_run_id"),
            robustness_run_ids=tuple(str(x) for x in raw.get("robustness_run_ids", [])),
            dataset_id=str(raw["dataset_id"]),
            dataset_content_hash=str(raw["dataset_content_hash"]),
            artifact_checksums={
                str(k): str(v) for k, v in raw.get("artifact_checksums", {}).items()
            },
            layer_refs=dict(raw.get("layer_refs") or {}),
            global_profile=dict(raw.get("global_profile") or {}),
            limitations=tuple(
                ScorecardLimitation.from_dict(x) for x in raw.get("limitations", [])
            ),
            decision_binding=bool(raw.get("decision_binding", False)),
            auto_promotion=bool(raw.get("auto_promotion", False)),
            promotion_action="none",
            status=raw.get("status", "active"),
            invalidation_reason=raw.get("invalidation_reason"),
        )


def compute_scorecard_id(
    *,
    run_id: str,
    policy_version: str,
    policy_content_hash: str,
    dataset_id: str,
    dataset_content_hash: str,
    layer_refs: Mapping[str, Any],
    gate_run_id: str | None = None,
    robustness_run_ids: Sequence[str] = (),
) -> str:
    payload = {
        "dataset_content_hash": dataset_content_hash,
        "dataset_id": dataset_id,
        "gate_run_id": gate_run_id,
        "layer_refs": layer_refs,
        "policy_content_hash": policy_content_hash,
        "policy_version": policy_version,
        "robustness_run_ids": sorted(robustness_run_ids),
        "run_id": run_id,
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sc_{digest}"


class ScorecardResultStore:
    """Append-only JSONL scorecard log (mirrors GateResultStore)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / "artifacts" / "research" / "scorecards" / "registry.jsonl"
        self.invalidation_dir = (
            self.root / "artifacts" / "research" / "scorecards" / "invalidations"
        )

    def _append_line(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def list_entries(self) -> list[ScorecardRecord]:
        if not self.path.exists():
            return []
        entries: list[ScorecardRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entries.append(ScorecardRecord.from_dict(json.loads(line)))
        return entries

    def get(self, scorecard_id: str) -> ScorecardRecord | None:
        matches = [e for e in self.list_entries() if e.scorecard_id == scorecard_id]
        return matches[-1] if matches else None

    def append(self, record: ScorecardRecord) -> None:
        existing = self.get(record.scorecard_id)
        if existing is not None and existing.status == "active":
            msg = f"duplicate active scorecard_id forbidden: {record.scorecard_id}"
            raise ValueError(msg)
        self._append_line(record.to_dict())

    def invalidate(self, scorecard_id: str, *, reason: str, actor: str) -> Path:
        entry = self.get(scorecard_id)
        if entry is None:
            raise KeyError(scorecard_id)
        if entry.status == "invalidated":
            msg = f"scorecard already invalidated: {scorecard_id}"
            raise ValueError(msg)
        self.invalidation_dir.mkdir(parents=True, exist_ok=True)
        sidecar = self.invalidation_dir / f"{scorecard_id}.jsonl"
        sidecar_record = {
            "provenance": {"actor": actor, "at": _utc_now()},
            "reason": reason,
            "scorecard_id": scorecard_id,
            "status": "invalidated",
        }
        with sidecar.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sidecar_record, sort_keys=True) + "\n")
        superseding = replace(entry, status="invalidated", invalidation_reason=reason)
        self._append_line(superseding.to_dict())
        return sidecar


def verify_scorecard_record_artifact_checksums(root: Path, record: ScorecardRecord) -> None:
    """Re-verify run artifact checksums bound on the scorecard record."""
    registry = ExperimentRegistry(root.resolve())
    try:
        entry = registry.show(record.run_id, verify=True)
    except KeyError as exc:
        raise ScorecardEvaluationError(
            f"scorecard run_id not in registry: {record.run_id}",
            field_errors={"artifact_checksums": "run missing"},
        ) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise ScorecardEvaluationError(
            f"scorecard run artifact seal failed: {exc}",
            field_errors={"artifact_checksums": "run checksum mismatch"},
        ) from exc

    run_checksums = {
        k: v for k, v in record.artifact_checksums.items() if not k.startswith("scorecard/")
    }
    if not run_checksums:
        raise ScorecardEvaluationError(
            "scorecard record has no run artifact_checksums",
            field_errors={"artifact_checksums": "empty run checksums"},
        )
    try:
        verify_checksums_against(Path(entry.artifact_path), run_checksums)
    except (ValueError, FileNotFoundError) as exc:
        raise ScorecardEvaluationError(
            f"scorecard artifact_checksums mismatch vs current run files: {exc}",
            field_errors={"artifact_checksums": "run file mismatch"},
        ) from exc

    if record.gate_run_id:
        gate = GateResultStore(root).get(record.gate_run_id)
        if gate is None:
            raise ScorecardEvaluationError(
                f"scorecard gate_run_id not found: {record.gate_run_id}",
                field_errors={"gate_run_id": "missing"},
            )
        try:
            verify_gate_record_artifact_checksums(root, gate)
        except Exception as exc:  # GateEvaluationError
            raise ScorecardEvaluationError(
                f"scorecard bound gate evidence untrusted: {exc}",
                field_errors={"gate_run_id": "checksum mismatch"},
            ) from exc


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScorecardEvaluationError(
            f"artifact is not a JSON object: {path.name}",
            field_errors={"artifacts": path.name},
        )
    return raw


def _layer_file_digest(artifact_path: Path, filename: str, checksums: Mapping[str, str]) -> str:
    if filename not in checksums:
        raise ScorecardEvaluationError(
            f"registry checksums missing {filename}",
            field_errors={"artifact_checksums": f"missing {filename}"},
        )
    path = artifact_path / filename
    if not path.is_file():
        raise ScorecardEvaluationError(
            f"required layer artifact missing: {filename}",
            field_errors={"artifacts": filename},
        )
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = checksums[filename]
    if actual != expected:
        raise ScorecardEvaluationError(
            f"layer artifact checksum mismatch for {filename}",
            field_errors={"artifact_checksums": f"mismatch {filename}"},
        )
    return expected


class ScorecardEvaluator:
    """Assemble Layer-5 scorecard from sealed run (+ optional gate) evidence."""

    def __init__(self, root: Path, *, repo_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or self.root).resolve()
        self.registry = ExperimentRegistry(self.root)
        self.store = ScorecardResultStore(self.root)
        self.gates = GateResultStore(self.root)

    def evaluate(
        self,
        *,
        run_id: str,
        policy_version: str = "1.0",
        gate_run_id: str | None = None,
        robustness_run_ids: Sequence[str] = (),
    ) -> ScorecardRecord:
        try:
            policy: ScorecardPolicy = get_scorecard_policy(policy_version)
        except ScorecardPolicyError as exc:
            raise ScorecardEvaluationError(
                str(exc), field_errors={"policy_version": "unknown"}
            ) from exc
        policy_hash = compute_scorecard_policy_content_hash(policy)

        try:
            entry = self.registry.show(run_id, verify=True)
        except KeyError as exc:
            raise ScorecardEvaluationError(
                f"run_id not found: {run_id}", field_errors={"run_id": "not found"}
            ) from exc
        except (ValueError, FileNotFoundError) as exc:
            raise ScorecardEvaluationError(
                f"run checksum verify failed: {exc}",
                field_errors={"run_id": "checksum mismatch"},
            ) from exc
        if entry.status != "complete":
            raise ScorecardEvaluationError(
                f"run_id {run_id} is not complete (status={entry.status})",
                field_errors={"run_id": f"status={entry.status}"},
            )

        artifact_path = Path(entry.artifact_path)
        manifest = load_run_manifest(artifact_path / "run_manifest.json")
        checksums = dict(entry.checksums)

        limitations: list[ScorecardLimitation] = []
        layer_refs: dict[str, Any] = {}

        # Required layers
        labels = _load_json(artifact_path / "regime_labels.json")
        _layer_file_digest(artifact_path, "regime_labels.json", checksums)
        layer_refs["classification_id"] = labels.get("classification_id")
        layer_refs["classifier_version"] = labels.get("classifier_version")
        layer_refs["classifier_content_hash"] = labels.get("classifier_content_hash")

        metrics = _load_json(artifact_path / "regime_metrics.json")
        _layer_file_digest(artifact_path, "regime_metrics.json", checksums)
        layer_refs["quality_id"] = metrics.get("quality_id")
        layer_refs["score_policy_version"] = metrics.get("score_policy_version")
        layer_refs["score_policy_content_hash"] = metrics.get("score_policy_content_hash")

        behaviour = _load_json(artifact_path / "behavior_profile.json")
        _layer_file_digest(artifact_path, "behavior_profile.json", checksums)
        layer_refs["behaviour_id"] = behaviour.get("behaviour_id")
        layer_refs["behaviour_policy_version"] = behaviour.get("policy_version")
        layer_refs["behaviour_policy_content_hash"] = behaviour.get("policy_content_hash")

        # Confidence: prefer sealed file; else derive (not written back to run dir).
        confidence_payload: dict[str, Any]
        if (artifact_path / "confidence_profile.json").is_file():
            _layer_file_digest(artifact_path, "confidence_profile.json", checksums)
            confidence_payload = _load_json(artifact_path / "confidence_profile.json")
            layer_refs["confidence_source"] = "run_artifact"
        else:
            confidence_payload = self._derive_confidence(
                artifact_path=artifact_path,
                entry=entry,
                manifest_dataset_id=manifest.dataset_id,
                manifest_dataset_hash=manifest.dataset_content_hash,
                gate_run_id=gate_run_id,
                robustness_run_ids=tuple(sorted(robustness_run_ids)),
            )
            layer_refs["confidence_source"] = "derived_at_scorecard"
            limitations.append(
                ScorecardLimitation(
                    code="confidence_profile",
                    status="DERIVED",
                    detail=(
                        "confidence_profile.json absent from run dir; derived at "
                        "scorecard evaluate time (not written back to run artifacts)"
                    ),
                )
            )
        layer_refs["confidence_id"] = confidence_payload.get("confidence_id")
        layer_refs["confidence_policy_version"] = confidence_payload.get("policy_version")
        layer_refs["confidence_policy_content_hash"] = confidence_payload.get(
            "policy_content_hash"
        )
        layer_refs["confidence_overall_label"] = confidence_payload.get("overall_label")

        # Parameter area (#290) — optional / NOT_AVAILABLE
        parameter_area: dict[str, Any]
        if (artifact_path / "parameter_area.json").is_file():
            _layer_file_digest(artifact_path, "parameter_area.json", checksums)
            parameter_area = _load_json(artifact_path / "parameter_area.json")
            layer_refs["parameter_area_id"] = parameter_area.get("parameter_area_id")
        else:
            parameter_area = {
                "classification": None,
                "limitation": "parameter_area.json not produced (#290)",
                "status": "NOT_AVAILABLE",
            }
            layer_refs["parameter_area_id"] = None
            limitations.append(
                ScorecardLimitation(
                    code="parameter_area",
                    status="NOT_AVAILABLE",
                    detail="parameter_area.json not produced (#290)",
                )
            )

        gate_integrity = None
        gate_overall = None
        if gate_run_id:
            gate = self.gates.get(gate_run_id)
            if gate is None:
                raise ScorecardEvaluationError(
                    f"gate_run_id not found: {gate_run_id}",
                    field_errors={"gate_run_id": "not found"},
                )
            if gate.run_id != run_id:
                raise ScorecardEvaluationError(
                    f"gate_run_id {gate_run_id} bound to run {gate.run_id}, not {run_id}",
                    field_errors={"gate_run_id": "run_id mismatch"},
                )
            if gate.status != "active":
                raise ScorecardEvaluationError(
                    f"gate_run_id {gate_run_id} is not active",
                    field_errors={"gate_run_id": f"status={gate.status}"},
                )
            try:
                verify_gate_record_artifact_checksums(self.root, gate)
            except Exception as exc:
                raise ScorecardEvaluationError(
                    f"gate evidence untrusted: {exc}",
                    field_errors={"gate_run_id": "checksum mismatch"},
                ) from exc
            gate_integrity = gate.integrity_status
            gate_overall = gate.overall_status
            layer_refs["gate_policy_version"] = gate.policy_version
            layer_refs["gate_policy_content_hash"] = gate.policy_content_hash
            layer_refs["gate_integrity_status"] = gate.integrity_status
            layer_refs["gate_overall_status"] = gate.overall_status

        sorted_rob = tuple(sorted(robustness_run_ids))
        evaluation_code_commit = _resolve_evaluation_code_commit(self.repo_root)

        global_profile = {
            "auto_promotion": False,
            "behaviour": {
                "behaviour_id": behaviour.get("behaviour_id"),
                "main_strength": behaviour.get("main_strength"),
                "main_weakness": behaviour.get("main_weakness"),
                "transition_risk": behaviour.get("transition_risk"),
            },
            "confidence": {
                "confidence_id": confidence_payload.get("confidence_id"),
                "overall_label": confidence_payload.get("overall_label"),
                "source": layer_refs["confidence_source"],
            },
            "decision_binding": False,
            "gates": {
                "gate_run_id": gate_run_id,
                "integrity_status": gate_integrity,
                "overall_status": gate_overall,
            },
            "parameter_area": parameter_area,
            "quality": {
                "quality_id": metrics.get("quality_id"),
                "strongest_regime": metrics.get("strongest_regime"),
                "worst_regime": metrics.get("worst_regime"),
            },
            "regime": {
                "classification_id": labels.get("classification_id"),
                "classifier_version": labels.get("classifier_version"),
            },
            "robustness_run_ids": list(sorted_rob),
        }

        scorecard_id = compute_scorecard_id(
            run_id=run_id,
            policy_version=policy.version,
            policy_content_hash=policy_hash,
            dataset_id=manifest.dataset_id,
            dataset_content_hash=manifest.dataset_content_hash,
            layer_refs=layer_refs,
            gate_run_id=gate_run_id,
            robustness_run_ids=sorted_rob,
        )

        record = ScorecardRecord(
            schema_version=SCORECARD_RECORD_SCHEMA_VERSION,
            scorecard_id=scorecard_id,
            policy_version=policy.version,
            policy_content_hash=policy_hash,
            evaluated_at=_utc_now(),
            run_code_commit=manifest.git_commit,
            evaluation_code_commit=evaluation_code_commit,
            experiment_id=entry.experiment_id,
            run_id=run_id,
            gate_run_id=gate_run_id,
            robustness_run_ids=sorted_rob,
            dataset_id=manifest.dataset_id,
            dataset_content_hash=manifest.dataset_content_hash,
            artifact_checksums=checksums,
            layer_refs=layer_refs,
            global_profile=global_profile,
            limitations=tuple(limitations),
            decision_binding=False,
            auto_promotion=False,
            promotion_action="none",
            status="active",
        )

        existing = self.store.get(scorecard_id)
        if existing is not None and existing.status == "active":
            return existing
        self.store.append(record)
        return record

    def _derive_confidence(
        self,
        *,
        artifact_path: Path,
        entry: RegistryEntry,
        manifest_dataset_id: str,
        manifest_dataset_hash: str,
        gate_run_id: str | None,
        robustness_run_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        metrics_raw = _load_json(artifact_path / "metrics.json")
        closed_trades = metrics_raw.get("closed_trades")
        equity_periods = None
        equity_path = artifact_path / "equity.json"
        if equity_path.is_file():
            equity = json.loads(equity_path.read_text(encoding="utf-8"))
            if isinstance(equity, list) and len(equity) >= 1:
                equity_periods = max(0, len(equity) - 1)

        gate_integrity = None
        if gate_run_id:
            gate = self.gates.get(gate_run_id)
            if gate is not None:
                gate_integrity = gate.integrity_status

        inputs = ConfidenceEvidenceInputs(
            run_id=entry.run_id,
            experiment_id=entry.experiment_id,
            dataset_id=manifest_dataset_id,
            dataset_content_hash=manifest_dataset_hash,
            run_status=entry.status,
            closed_trades=int(closed_trades) if closed_trades is not None else None,
            equity_periods=equity_periods,
            gate_integrity_status=gate_integrity,
            robustness_run_ids=robustness_run_ids,
            gate_run_id=gate_run_id,
        )
        return evaluate_confidence(inputs).to_artifact()
