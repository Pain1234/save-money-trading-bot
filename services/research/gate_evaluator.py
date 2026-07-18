"""Gate evaluator + append-only gate persistence (Issue #248 / P4.7c).

Evaluates evidence already produced by the research runner (#141-#147) and
the robustness orchestrator (#247) against a versioned
:mod:`research.gate_policy`. This module does not run a second backtest
engine and performs **no** live/paper promotion: :attr:`GateRunRecord.
promotion_action` is always ``"none"`` and no code path here calls into
``paper_trading`` or any live order surface.

Evidence-binding contract (mandatory, #248) — every persisted
:class:`GateRunRecord` carries:

- ``run_id`` (+ optional ``robustness_run_ids``)
- ``artifact_checksums`` of every evaluated evidence file (registry trust
  anchor for the run + a SHA-256 seal per evaluated robustness manifest)
- ``dataset_id`` / ``dataset_content_hash`` (from the run's sealed
  ``RunManifest``)
- ``policy_version`` **and** ``policy_content_hash`` (not version alone —
  see :mod:`research.gate_policy`)
- ``run_code_commit`` (git SHA pinned at run time) and
  ``evaluation_code_commit`` (git SHA of the evaluator at evaluation time)

Persistence is append-only, mirroring ``research.registry``
(:class:`~research.registry.ExperimentRegistry`): gate results are never
mutated in place, and invalidation appends a superseding record plus a
sidecar — it never rewrites or deletes a prior record.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from research.gate_policy import (
    GatePolicy,
    GatePolicyError,
    compute_policy_content_hash,
    evaluate_comparator,
    get_policy,
)
from research.metrics_contract import ResearchMetrics, validate_metrics_or_mark_invalid
from research.registry import ExperimentRegistry, RegistryEntry
from research.robustness import robustness_manifest_path
from research.run_manifest import RunManifest, load_run_manifest
from research.runner import resolve_git_commit

GATE_RUN_RECORD_SCHEMA_VERSION = "1.0"
GateStatus = Literal["active", "invalidated"]
GateOverallStatus = Literal["pass", "fail"]


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class GateEvaluationError(Exception):
    """Evidence could not be resolved/bound for gate evaluation."""

    def __init__(self, message: str, *, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


@dataclass(frozen=True)
class GateEvaluationResult:
    """One evaluated gate within a :class:`GateRunRecord` (Gate-Name, Grenzwert,
    gemessener Wert, bestanden/nicht bestanden, Ablehnungsgrund)."""

    name: str
    threshold: str
    measured_value: str | None
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "measured_value": self.measured_value,
            "passed": self.passed,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> GateEvaluationResult:
        return cls(
            name=str(raw["name"]),
            threshold=str(raw["threshold"]),
            measured_value=raw.get("measured_value"),
            passed=bool(raw["passed"]),
            reason=str(raw["reason"]),
        )


@dataclass(frozen=True)
class GateRunRecord:
    """One append-only, immutable gate evaluation record."""

    schema_version: str
    gate_run_id: str
    policy_version: str
    policy_content_hash: str
    evaluated_at: str
    run_code_commit: str
    evaluation_code_commit: str
    experiment_id: str
    run_id: str
    robustness_run_ids: tuple[str, ...]
    dataset_id: str
    dataset_content_hash: str
    artifact_checksums: dict[str, str]
    measurements: dict[str, str]
    gates: tuple[GateEvaluationResult, ...]
    overall_status: GateOverallStatus
    promotion_action: Literal["none"] = "none"
    status: GateStatus = "active"
    invalidation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gate_run_id": self.gate_run_id,
            "policy_version": self.policy_version,
            "policy_content_hash": self.policy_content_hash,
            "evaluated_at": self.evaluated_at,
            "run_code_commit": self.run_code_commit,
            "evaluation_code_commit": self.evaluation_code_commit,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "robustness_run_ids": list(self.robustness_run_ids),
            "dataset_id": self.dataset_id,
            "dataset_content_hash": self.dataset_content_hash,
            "artifact_checksums": dict(sorted(self.artifact_checksums.items())),
            "measurements": dict(sorted(self.measurements.items())),
            "gates": [g.to_dict() for g in self.gates],
            "overall_status": self.overall_status,
            "promotion_action": self.promotion_action,
            "status": self.status,
            "invalidation_reason": self.invalidation_reason,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> GateRunRecord:
        return cls(
            schema_version=str(raw["schema_version"]),
            gate_run_id=str(raw["gate_run_id"]),
            policy_version=str(raw["policy_version"]),
            policy_content_hash=str(raw["policy_content_hash"]),
            evaluated_at=str(raw["evaluated_at"]),
            run_code_commit=str(raw["run_code_commit"]),
            evaluation_code_commit=str(raw["evaluation_code_commit"]),
            experiment_id=str(raw["experiment_id"]),
            run_id=str(raw["run_id"]),
            robustness_run_ids=tuple(str(x) for x in raw.get("robustness_run_ids", [])),
            dataset_id=str(raw["dataset_id"]),
            dataset_content_hash=str(raw["dataset_content_hash"]),
            artifact_checksums={
                str(k): str(v) for k, v in raw.get("artifact_checksums", {}).items()
            },
            measurements={str(k): str(v) for k, v in raw.get("measurements", {}).items()},
            gates=tuple(GateEvaluationResult.from_dict(g) for g in raw.get("gates", [])),
            overall_status=raw["overall_status"],
            promotion_action="none",
            status=raw.get("status", "active"),
            invalidation_reason=raw.get("invalidation_reason"),
        )


def compute_gate_run_id(
    *,
    run_id: str,
    policy_version: str,
    policy_content_hash: str,
    robustness_run_ids: Sequence[str] = (),
) -> str:
    """Deterministic gate_run_id — idempotent evaluate, mirrors experiment/robustness ids."""
    payload = {
        "run_id": run_id,
        "policy_version": policy_version,
        "policy_content_hash": policy_content_hash,
        "robustness_run_ids": sorted(robustness_run_ids),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"gate_{digest}"


class GateResultStore:
    """Append-only JSONL gate-result log, mirrors ``research.registry``."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / "artifacts" / "research" / "gates" / "registry.jsonl"
        self.invalidation_dir = self.root / "artifacts" / "research" / "gates" / "invalidations"

    def _append_line(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def list_entries(self) -> list[GateRunRecord]:
        if not self.path.exists():
            return []
        entries: list[GateRunRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entries.append(GateRunRecord.from_dict(json.loads(line)))
        return entries

    def get(self, gate_run_id: str) -> GateRunRecord | None:
        """Most recent record for ``gate_run_id`` (reflects invalidation if any)."""
        matches = [e for e in self.list_entries() if e.gate_run_id == gate_run_id]
        return matches[-1] if matches else None

    def list_for_run(self, run_id: str) -> list[GateRunRecord]:
        return [e for e in self.list_entries() if e.run_id == run_id]

    def append(self, record: GateRunRecord) -> None:
        existing = self.get(record.gate_run_id)
        if existing is not None and existing.status == "active":
            msg = f"duplicate active gate_run_id forbidden: {record.gate_run_id}"
            raise ValueError(msg)
        self._append_line(record.to_dict())

    def invalidate(self, gate_run_id: str, *, reason: str, actor: str) -> Path:
        """Append-only invalidation sidecar + superseding record (registry.invalidate pattern)."""
        entry = self.get(gate_run_id)
        if entry is None:
            raise KeyError(gate_run_id)
        if entry.status == "invalidated":
            msg = f"gate result already invalidated: {gate_run_id}"
            raise ValueError(msg)
        self.invalidation_dir.mkdir(parents=True, exist_ok=True)
        sidecar = self.invalidation_dir / f"{gate_run_id}.jsonl"
        sidecar_record = {
            "gate_run_id": gate_run_id,
            "status": "invalidated",
            "reason": reason,
            "provenance": {"actor": actor, "at": _utc_now()},
        }
        with sidecar.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sidecar_record, sort_keys=True) + "\n")
        superseding = replace(entry, status="invalidated", invalidation_reason=reason)
        self._append_line(superseding.to_dict())
        return sidecar


def _decimal_measurement(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _measurements_from_metrics(metrics: ResearchMetrics) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {"closed_trades": Decimal(metrics.closed_trades)}
    net_pnl = _decimal_measurement(metrics.net_pnl)
    if net_pnl is not None:
        out["net_pnl"] = net_pnl
    max_drawdown = _decimal_measurement(metrics.max_drawdown)
    if max_drawdown is not None:
        out["max_drawdown"] = max_drawdown
    return out


def _measurements_from_robustness_manifest(manifest: dict[str, Any]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    test_type = manifest.get("test_type")
    children = manifest.get("children") or []

    if test_type == "walk_forward":
        complete = [
            c
            for c in children
            if c.get("status") == "complete" and c.get("net_pnl") is not None
        ]
        if complete:
            complete_pnls = [_decimal_measurement(c["net_pnl"]) for c in complete]
            passed = sum(1 for pnl in complete_pnls if pnl is not None and pnl >= 0)
            out["walk_forward_fold_pass_ratio"] = Decimal(passed) / Decimal(len(complete))

    elif test_type == "cost_stress":
        for child in children:
            if child.get("child_id") == "combined_elevated" and child.get("net_pnl") is not None:
                value = _decimal_measurement(child["net_pnl"])
                if value is not None:
                    out["cost_stress_combined_elevated_net_pnl"] = value

    elif test_type == "parameter_stability":
        neighbors = [
            c
            for c in children
            if c.get("child_id") != "frozen"
            and c.get("status") == "complete"
            and c.get("net_pnl") is not None
        ]
        if neighbors:
            neighbor_pnls = [_decimal_measurement(c["net_pnl"]) for c in neighbors]
            passed = sum(1 for pnl in neighbor_pnls if pnl is not None and pnl >= 0)
            out["parameter_neighbor_pass_ratio"] = Decimal(passed) / Decimal(len(neighbors))

    elif test_type == "bootstrap":
        bootstrap_result = manifest.get("bootstrap_result") or {}
        quantiles = bootstrap_result.get("net_pnl_quantiles") or {}
        q05 = quantiles.get("q05")
        value = _decimal_measurement(q05)
        if value is not None:
            out["bootstrap_q05_net_pnl"] = value

    return out


class GateEvaluator:
    """Binds evidence for one run (+ optional robustness manifests) and applies
    a versioned :class:`~research.gate_policy.GatePolicy`. Read-only over
    already-produced artifacts; performs no auto-promotion."""

    def __init__(self, root: Path, *, repo_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or self.root).resolve()
        self.registry = ExperimentRegistry(self.root)
        self.store = GateResultStore(self.root)

    def _resolve_run(self, run_id: str) -> tuple[RegistryEntry, RunManifest, ResearchMetrics]:
        try:
            entry = self.registry.show(run_id, verify=True)
        except KeyError as exc:
            raise GateEvaluationError(
                f"run_id not found in registry: {run_id}",
                field_errors={"run_id": "not found"},
            ) from exc
        if entry.status != "complete":
            raise GateEvaluationError(
                f"run_id {run_id} is not in status 'complete' (status={entry.status})",
                field_errors={"run_id": f"status={entry.status}"},
            )
        artifact_path = Path(entry.artifact_path)
        manifest = load_run_manifest(artifact_path / "run_manifest.json")
        metrics_raw = json.loads((artifact_path / "metrics.json").read_text(encoding="utf-8"))
        try:
            metrics = validate_metrics_or_mark_invalid(metrics_raw)
        except ValueError as exc:
            raise GateEvaluationError(
                f"metrics.json failed contract validation for run_id {run_id}: {exc}",
                field_errors={"run_id": "invalid metrics contract"},
            ) from exc
        return entry, manifest, metrics

    def _load_robustness_evidence(
        self, robustness_run_ids: Sequence[str]
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        manifests: dict[str, dict[str, Any]] = {}
        checksums: dict[str, str] = {}
        for robustness_id in robustness_run_ids:
            path = robustness_manifest_path(self.root, robustness_id)
            if not path.is_file():
                raise GateEvaluationError(
                    f"robustness manifest not found: {robustness_id}",
                    field_errors={"robustness_run_ids": f"missing: {robustness_id}"},
                )
            raw_bytes = path.read_bytes()
            checksums[f"robustness/{robustness_id}/manifest.json"] = hashlib.sha256(
                raw_bytes
            ).hexdigest()
            manifests[robustness_id] = json.loads(raw_bytes)
        return manifests, checksums

    def evaluate(
        self,
        *,
        run_id: str,
        policy_version: str,
        robustness_run_ids: Sequence[str] = (),
    ) -> GateRunRecord:
        try:
            policy: GatePolicy = get_policy(policy_version)
        except GatePolicyError as exc:
            raise GateEvaluationError(
                str(exc), field_errors={"policy_version": "unknown"}
            ) from exc
        policy_content_hash = compute_policy_content_hash(policy)

        entry, manifest, metrics = self._resolve_run(run_id)
        robustness_manifests, robustness_checksums = self._load_robustness_evidence(
            robustness_run_ids
        )

        measurements = _measurements_from_metrics(metrics)
        for robustness_manifest in robustness_manifests.values():
            measurements.update(_measurements_from_robustness_manifest(robustness_manifest))

        gate_results: list[GateEvaluationResult] = []
        for gate in policy.gates:
            measured = measurements.get(gate.metric)
            if measured is None:
                gate_results.append(
                    GateEvaluationResult(
                        name=gate.name,
                        threshold=gate.threshold,
                        measured_value=None,
                        passed=False,
                        reason=f"no evidence available for metric '{gate.metric}'",
                    )
                )
                continue
            threshold_decimal = Decimal(gate.threshold)
            passed = evaluate_comparator(gate.comparator, measured, threshold_decimal)
            reason = (
                "pass"
                if passed
                else (
                    f"{gate.name}: measured {measured} does not satisfy "
                    f"{gate.comparator} {gate.threshold}"
                )
            )
            gate_results.append(
                GateEvaluationResult(
                    name=gate.name,
                    threshold=gate.threshold,
                    measured_value=format(measured, "f"),
                    passed=passed,
                    reason=reason,
                )
            )

        overall_status: GateOverallStatus = (
            "pass" if all(g.passed for g in gate_results) else "fail"
        )

        try:
            evaluation_code_commit = resolve_git_commit(self.repo_root, allow_dirty=True)
        except ValueError:
            # Deploy images without .git and without an env pin: fall back to
            # the run's own sealed commit rather than failing evaluation.
            evaluation_code_commit = manifest.git_commit

        artifact_checksums = dict(entry.checksums)
        artifact_checksums.update(robustness_checksums)

        sorted_robustness_ids = tuple(sorted(robustness_run_ids))
        gate_run_id = compute_gate_run_id(
            run_id=run_id,
            policy_version=policy_version,
            policy_content_hash=policy_content_hash,
            robustness_run_ids=sorted_robustness_ids,
        )

        record = GateRunRecord(
            schema_version=GATE_RUN_RECORD_SCHEMA_VERSION,
            gate_run_id=gate_run_id,
            policy_version=policy_version,
            policy_content_hash=policy_content_hash,
            evaluated_at=_utc_now(),
            run_code_commit=manifest.git_commit,
            evaluation_code_commit=evaluation_code_commit,
            experiment_id=entry.experiment_id,
            run_id=run_id,
            robustness_run_ids=sorted_robustness_ids,
            dataset_id=manifest.dataset_id,
            dataset_content_hash=manifest.dataset_content_hash,
            artifact_checksums=artifact_checksums,
            measurements={k: format(v, "f") for k, v in measurements.items()},
            gates=tuple(gate_results),
            overall_status=overall_status,
            promotion_action="none",
            status="active",
        )

        existing = self.store.get(gate_run_id)
        if existing is not None and existing.status == "active":
            return existing
        self.store.append(record)
        return record
