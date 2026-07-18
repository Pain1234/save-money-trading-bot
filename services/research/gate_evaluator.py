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
  ``evaluation_code_commit`` (deploy pin via ``RESEARCH_EVALUATION_GIT_SHA`` /
  ``RAILWAY_GIT_COMMIT_SHA``, else clean ``git rev-parse HEAD`` — never the
  evaluated run's commit)

Persistence is append-only, mirroring ``research.registry``
(:class:`~research.registry.ExperimentRegistry`): gate results are never
mutated in place, and invalidation appends a superseding record plus a
sidecar — it never rewrites or deletes a prior record.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from research.artifacts import verify_checksums_against
from research.gate_policy import (
    GatePolicy,
    GatePolicyError,
    compute_policy_content_hash,
    evaluate_comparator,
    get_policy,
)
from research.metrics_contract import ResearchMetrics, validate_metrics_or_mark_invalid
from research.registry import ExperimentRegistry, RegistryEntry
from research.robustness import (
    ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
    compute_bootstrap_from_equity_artifact,
    robustness_manifest_path,
    verify_robustness_manifest_seal,
)
from research.robustness_jobs import RobustnessJobStore
from research.run_manifest import RunManifest, load_run_manifest
from research.runner import resolve_git_commit
from research.write_service import load_dataset_catalog

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


def _resolve_evaluation_code_commit(repo_root: Path) -> str:
    """Pin the evaluator binary/image commit; dirty trees fail closed.

    Preference order:
    1. ``RESEARCH_EVALUATION_GIT_SHA`` / ``RAILWAY_GIT_COMMIT_SHA`` (deploy pin)
    2. ``resolve_git_commit(repo_root, allow_dirty=False)``

    Never falls back to the evaluated run's ``git_commit``.
    """
    for key in ("RESEARCH_EVALUATION_GIT_SHA", "RAILWAY_GIT_COMMIT_SHA"):
        pinned = (os.environ.get(key) or "").strip()
        if pinned:
            return pinned
    return resolve_git_commit(repo_root, allow_dirty=False)


def _child_net_pnl_from_verified_run(
    registry: ExperimentRegistry,
    *,
    robustness_id: str,
    child: dict[str, Any],
) -> Decimal:
    """Load ``net_pnl`` from the child's sealed ``metrics.json`` (not the manifest copy)."""
    child_id = child.get("child_id")
    child_run_id = child.get("run_id")
    if not child_run_id:
        raise GateEvaluationError(
            f"robustness {robustness_id} child {child_id!r} is missing run_id",
            field_errors={"robustness_run_ids": "child run_id missing"},
        )
    try:
        entry = registry.show(str(child_run_id), verify=True)
    except KeyError as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} child run_id not in registry: {child_run_id}",
            field_errors={"robustness_run_ids": "child run missing"},
        ) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} child run_id checksum verify failed: "
            f"{child_run_id}: {exc}",
            field_errors={"robustness_run_ids": "child checksum mismatch"},
        ) from exc
    metrics_path = Path(entry.artifact_path) / "metrics.json"
    try:
        metrics_raw = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics = validate_metrics_or_mark_invalid(metrics_raw)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} child {child_run_id} metrics.json "
            f"failed validation: {exc}",
            field_errors={"robustness_run_ids": "child metrics invalid"},
        ) from exc
    metrics_pnl = _decimal_measurement(metrics.net_pnl)
    if metrics_pnl is None:
        raise GateEvaluationError(
            f"robustness {robustness_id} child {child_run_id} metrics.json "
            "is missing net_pnl",
            field_errors={"robustness_run_ids": "child net_pnl missing"},
        )
    manifest_pnl = _decimal_measurement(child.get("net_pnl"))
    if manifest_pnl is not None and manifest_pnl != metrics_pnl:
        raise GateEvaluationError(
            f"robustness {robustness_id} child {child_id!r} manifest net_pnl="
            f"{manifest_pnl} disagrees with sealed metrics.json net_pnl="
            f"{metrics_pnl} (fail closed)",
            field_errors={"robustness_run_ids": "child net_pnl mismatch"},
        )
    return metrics_pnl


def _measurements_from_robustness_manifest(
    registry: ExperimentRegistry,
    manifest: dict[str, Any],
    *,
    robustness_id: str,
    base_run_id: str,
) -> dict[str, Decimal]:
    """Derive gate measurements from verified run artifacts, not mutable manifest copies.

    Walk-forward / cost-stress / parameter-stability load ``net_pnl`` from each
    child's sealed ``metrics.json`` via ``registry.show(..., verify=True)``.
    Bootstrap recomputes q05 from the sealed base-run ``equity.json``.
    """
    out: dict[str, Decimal] = {}
    test_type = manifest.get("test_type")
    children = manifest.get("children") or []

    if test_type == "walk_forward":
        complete = [c for c in children if isinstance(c, dict) and c.get("status") == "complete"]
        if complete:
            complete_pnls = [
                _child_net_pnl_from_verified_run(
                    registry, robustness_id=robustness_id, child=c
                )
                for c in complete
            ]
            passed = sum(1 for pnl in complete_pnls if pnl >= 0)
            out["walk_forward_fold_pass_ratio"] = Decimal(passed) / Decimal(len(complete))

    elif test_type == "cost_stress":
        for child in children:
            if not isinstance(child, dict):
                continue
            if child.get("child_id") == "combined_elevated" and child.get("status") == "complete":
                out["cost_stress_combined_elevated_net_pnl"] = _child_net_pnl_from_verified_run(
                    registry, robustness_id=robustness_id, child=child
                )

    elif test_type == "parameter_stability":
        neighbors = [
            c
            for c in children
            if isinstance(c, dict)
            and c.get("child_id") != "frozen"
            and c.get("status") == "complete"
        ]
        if neighbors:
            neighbor_pnls = [
                _child_net_pnl_from_verified_run(
                    registry, robustness_id=robustness_id, child=c
                )
                for c in neighbors
            ]
            passed = sum(1 for pnl in neighbor_pnls if pnl >= 0)
            out["parameter_neighbor_pass_ratio"] = Decimal(passed) / Decimal(len(neighbors))

    elif test_type == "bootstrap":
        out["bootstrap_q05_net_pnl"] = _bootstrap_q05_from_sealed_equity(
            registry,
            manifest,
            robustness_id=robustness_id,
            base_run_id=base_run_id,
        )

    return out


def _bootstrap_q05_from_sealed_equity(
    registry: ExperimentRegistry,
    manifest: dict[str, Any],
    *,
    robustness_id: str,
    base_run_id: str,
) -> Decimal:
    """Recompute bootstrap q05 from sealed equity; fail closed on sealed-result drift."""
    config = manifest.get("config") or {}
    if not isinstance(config, dict):
        raise GateEvaluationError(
            f"robustness {robustness_id} bootstrap config is invalid",
            field_errors={"robustness_run_ids": "invalid bootstrap config"},
        )
    try:
        block_length = int(config["block_length"])
        n_simulations = int(config["n_simulations"])
        seed = int(config["seed"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} bootstrap config missing "
            f"block_length/n_simulations/seed: {exc}",
            field_errors={"robustness_run_ids": "incomplete bootstrap config"},
        ) from exc
    quantiles_raw = config.get("quantiles", (0.05, 0.5, 0.95))
    try:
        quantiles = tuple(float(q) for q in quantiles_raw)
    except (TypeError, ValueError) as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} bootstrap quantiles invalid: {exc}",
            field_errors={"robustness_run_ids": "invalid bootstrap quantiles"},
        ) from exc

    try:
        entry = registry.show(base_run_id, verify=True)
    except KeyError as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} base_run_id not in registry: {base_run_id}",
            field_errors={"robustness_run_ids": "base run missing"},
        ) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} base_run_id checksum verify failed: "
            f"{base_run_id}: {exc}",
            field_errors={"robustness_run_ids": "base checksum mismatch"},
        ) from exc

    try:
        stats = compute_bootstrap_from_equity_artifact(
            Path(entry.artifact_path),
            block_length=block_length,
            n_simulations=n_simulations,
            seed=seed,
            quantiles=quantiles,
        )
    except (OSError, ValueError, FileNotFoundError) as exc:
        raise GateEvaluationError(
            f"robustness {robustness_id} bootstrap recompute from equity.json "
            f"failed: {exc}",
            field_errors={"robustness_run_ids": "bootstrap recompute failed"},
        ) from exc

    recomputed_q05 = _decimal_measurement(stats.net_pnl_quantiles.get("q05"))
    if recomputed_q05 is None:
        raise GateEvaluationError(
            f"robustness {robustness_id} bootstrap recompute missing q05",
            field_errors={"robustness_run_ids": "bootstrap q05 missing"},
        )

    sealed = manifest.get("bootstrap_result") or {}
    sealed_q05 = _decimal_measurement((sealed.get("net_pnl_quantiles") or {}).get("q05"))
    if sealed_q05 is None:
        raise GateEvaluationError(
            f"robustness {robustness_id} sealed bootstrap_result missing q05",
            field_errors={"robustness_run_ids": "sealed bootstrap q05 missing"},
        )
    # Float JSON round-trip can introduce tiny representation drift; reject
    # meaningful disagreement while tolerating sub-ulp stringification noise.
    if abs(sealed_q05 - recomputed_q05) > Decimal("1e-9"):
        raise GateEvaluationError(
            f"robustness {robustness_id} sealed bootstrap q05={sealed_q05} "
            f"disagrees with recomputation q05={recomputed_q05} (fail closed)",
            field_errors={"robustness_run_ids": "bootstrap q05 mismatch"},
        )
    return recomputed_q05


def verify_gate_record_artifact_checksums(root: Path, record: GateRunRecord) -> None:
    """Re-verify a persisted record's ``artifact_checksums`` against on-disk seals.

    Raises :class:`GateEvaluationError` on any mismatch (fail closed).
    """
    registry = ExperimentRegistry(root.resolve())
    try:
        entry = registry.show(record.run_id, verify=True)
    except KeyError as exc:
        raise GateEvaluationError(
            f"gate record run_id not in registry: {record.run_id}",
            field_errors={"artifact_checksums": "run missing"},
        ) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise GateEvaluationError(
            f"gate record run artifact seal failed: {exc}",
            field_errors={"artifact_checksums": "run checksum mismatch"},
        ) from exc

    run_checksums = {
        k: v for k, v in record.artifact_checksums.items() if not k.startswith("robustness/")
    }
    if not run_checksums:
        raise GateEvaluationError(
            "gate record has no run artifact_checksums",
            field_errors={"artifact_checksums": "empty run checksums"},
        )
    try:
        verify_checksums_against(Path(entry.artifact_path), run_checksums)
    except (ValueError, FileNotFoundError) as exc:
        raise GateEvaluationError(
            f"gate record artifact_checksums mismatch vs current run files: {exc}",
            field_errors={"artifact_checksums": "run file mismatch"},
        ) from exc

    for key, digest in record.artifact_checksums.items():
        if not key.startswith("robustness/") or not key.endswith("/manifest.json"):
            continue
        parts = key.split("/")
        if len(parts) != 3:
            raise GateEvaluationError(
                f"gate record has malformed robustness checksum key: {key!r}",
                field_errors={"artifact_checksums": "malformed robustness key"},
            )
        robustness_id = parts[1]
        try:
            verify_robustness_manifest_seal(
                root.resolve(), robustness_id, expected_hash=digest
            )
        except (ValueError, FileNotFoundError) as exc:
            raise GateEvaluationError(
                f"gate record robustness manifest seal failed for {robustness_id}: {exc}",
                field_errors={"artifact_checksums": "robustness seal mismatch"},
            ) from exc

    for robustness_id in record.robustness_run_ids:
        key = f"robustness/{robustness_id}/manifest.json"
        if key not in record.artifact_checksums:
            raise GateEvaluationError(
                f"gate record missing checksum for robustness {robustness_id}",
                field_errors={"artifact_checksums": "robustness checksum missing"},
            )


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

    def _verify_robustness_job_completed(self, robustness_id: str) -> None:
        """Fail closed unless the #247 job is ``completed`` (when a job exists).

        Synthetic fixture manifests without a job file are accepted only when
        the manifest summary itself reports a successful completion
        (``n_failed == 0``); incomplete children remain fail-closed via
        :meth:`_verify_robustness_children`.
        """
        job = RobustnessJobStore(self.root).get(robustness_id)
        if job is None:
            return
        if job.status != "completed":
            raise GateEvaluationError(
                f"robustness job {robustness_id} is not completed "
                f"(status={job.status})",
                field_errors={"robustness_run_ids": f"status={job.status}"},
            )

    def _verify_robustness_manifest_seal(self, robustness_id: str) -> str:
        """Fail closed unless the sealed manifest trust anchor still matches."""
        job = RobustnessJobStore(self.root).get(robustness_id)
        expected_hash = job.manifest_content_hash if job is not None else None
        try:
            return verify_robustness_manifest_seal(
                self.root, robustness_id, expected_hash=expected_hash
            )
        except (ValueError, FileNotFoundError) as exc:
            raise GateEvaluationError(
                f"robustness {robustness_id} manifest seal verification failed: {exc}",
                field_errors={"robustness_run_ids": "manifest seal mismatch"},
            ) from exc

    def _verify_robustness_dataset_binding(
        self,
        manifest: dict[str, Any],
        *,
        robustness_id: str,
        base_manifest: RunManifest,
    ) -> None:
        catalog_id = manifest.get("dataset_catalog_id")
        if catalog_id is None or str(catalog_id).strip() == "":
            # Bootstrap / fixture path: dataset is the base run's sealed
            # binding by construction once base_run_id is pinned.
            return
        catalog = {e.id: e for e in load_dataset_catalog()}
        entry = catalog.get(str(catalog_id))
        if entry is None:
            raise GateEvaluationError(
                f"robustness {robustness_id} references unknown "
                f"dataset_catalog_id={catalog_id!r}",
                field_errors={"robustness_run_ids": "unknown dataset_catalog_id"},
            )
        if entry.dataset_id != base_manifest.dataset_id:
            raise GateEvaluationError(
                f"robustness {robustness_id} dataset_id mismatch: "
                f"catalog={entry.dataset_id!r} base_run={base_manifest.dataset_id!r}",
                field_errors={"robustness_run_ids": "dataset_id mismatch"},
            )
        if entry.content_hash != base_manifest.dataset_content_hash:
            raise GateEvaluationError(
                f"robustness {robustness_id} dataset_content_hash mismatch: "
                f"catalog={entry.content_hash!r} "
                f"base_run={base_manifest.dataset_content_hash!r}",
                field_errors={"robustness_run_ids": "dataset_content_hash mismatch"},
            )

    def _verify_robustness_children(
        self,
        manifest: dict[str, Any],
        *,
        robustness_id: str,
        base_manifest: RunManifest,
    ) -> None:
        """Fail closed on incomplete children and verify complete child run seals."""
        children = manifest.get("children") or []
        if not isinstance(children, list):
            raise GateEvaluationError(
                f"robustness {robustness_id} has invalid children payload",
                field_errors={"robustness_run_ids": "invalid children"},
            )
        summary = manifest.get("summary") or {}
        n_failed = summary.get("n_failed")
        if n_failed is None:
            n_failed = sum(1 for c in children if c.get("status") != "complete")
        if int(n_failed) > 0:
            raise GateEvaluationError(
                f"robustness {robustness_id} has incomplete children "
                f"(n_failed={n_failed}); gate evaluation fails closed",
                field_errors={"robustness_run_ids": "incomplete children"},
            )
        for child in children:
            if not isinstance(child, dict):
                raise GateEvaluationError(
                    f"robustness {robustness_id} has invalid child entry",
                    field_errors={"robustness_run_ids": "invalid child"},
                )
            status = child.get("status")
            if status != "complete":
                raise GateEvaluationError(
                    f"robustness {robustness_id} child "
                    f"{child.get('child_id')!r} is not complete (status={status})",
                    field_errors={"robustness_run_ids": "incomplete children"},
                )
            child_run_id = child.get("run_id")
            if not child_run_id:
                raise GateEvaluationError(
                    f"robustness {robustness_id} complete child "
                    f"{child.get('child_id')!r} is missing run_id",
                    field_errors={"robustness_run_ids": "child run_id missing"},
                )
            try:
                child_entry = self.registry.show(str(child_run_id), verify=True)
            except KeyError as exc:
                raise GateEvaluationError(
                    f"robustness {robustness_id} child run_id not in registry: "
                    f"{child_run_id}",
                    field_errors={"robustness_run_ids": "child run missing"},
                ) from exc
            except ValueError as exc:
                raise GateEvaluationError(
                    f"robustness {robustness_id} child run_id checksum verify "
                    f"failed: {child_run_id}: {exc}",
                    field_errors={"robustness_run_ids": "child checksum mismatch"},
                ) from exc
            if child_entry.status != "complete":
                raise GateEvaluationError(
                    f"robustness {robustness_id} child run_id {child_run_id} "
                    f"is not complete (status={child_entry.status})",
                    field_errors={"robustness_run_ids": "child run incomplete"},
                )
            child_run_manifest = load_run_manifest(
                Path(child_entry.artifact_path) / "run_manifest.json"
            )
            if child_run_manifest.dataset_id != base_manifest.dataset_id:
                raise GateEvaluationError(
                    f"robustness {robustness_id} child {child_run_id} "
                    f"dataset_id mismatch vs base run",
                    field_errors={"robustness_run_ids": "child dataset_id mismatch"},
                )
            if child_run_manifest.dataset_content_hash != base_manifest.dataset_content_hash:
                raise GateEvaluationError(
                    f"robustness {robustness_id} child {child_run_id} "
                    f"dataset_content_hash mismatch vs base run",
                    field_errors={
                        "robustness_run_ids": "child dataset_content_hash mismatch"
                    },
                )

    def _validate_robustness_manifest(
        self,
        raw: dict[str, Any],
        *,
        robustness_id: str,
        run_id: str,
        base_manifest: RunManifest,
    ) -> None:
        schema_version = str(raw.get("schema_version") or "")
        if schema_version != ROBUSTNESS_MANIFEST_SCHEMA_VERSION:
            raise GateEvaluationError(
                f"robustness {robustness_id} has unsupported schema_version="
                f"{schema_version!r} (expected {ROBUSTNESS_MANIFEST_SCHEMA_VERSION!r})",
                field_errors={"robustness_run_ids": "unsupported schema_version"},
            )
        manifest_id = str(raw.get("robustness_id") or "")
        if manifest_id != robustness_id:
            raise GateEvaluationError(
                f"robustness manifest id mismatch: path={robustness_id!r} "
                f"manifest={manifest_id!r}",
                field_errors={"robustness_run_ids": "robustness_id mismatch"},
            )
        base_run_id = raw.get("base_run_id")
        if base_run_id is None or str(base_run_id) != run_id:
            raise GateEvaluationError(
                f"robustness {robustness_id} base_run_id={base_run_id!r} "
                f"does not match evaluated run_id={run_id!r} "
                "(cross-run evidence rejected)",
                field_errors={"robustness_run_ids": "base_run_id mismatch"},
            )
        self._verify_robustness_job_completed(robustness_id)
        self._verify_robustness_dataset_binding(
            raw, robustness_id=robustness_id, base_manifest=base_manifest
        )
        self._verify_robustness_children(
            raw, robustness_id=robustness_id, base_manifest=base_manifest
        )

    def _load_robustness_evidence(
        self,
        robustness_run_ids: Sequence[str],
        *,
        run_id: str,
        base_manifest: RunManifest,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Load and fail-closed-validate robustness manifests for ``run_id``.

        Rejects cross-run evidence, duplicate ``test_type`` manifests (no
        silent overwrite of measured values), incomplete children, and
        dataset / checksum mismatches. Sorting of ``robustness_run_ids`` for
        ``gate_run_id`` must not hide duplicate test types — duplicates are
        detected here before any measurement merge.
        """
        if len(set(robustness_run_ids)) != len(list(robustness_run_ids)):
            raise GateEvaluationError(
                "duplicate robustness_run_ids are not allowed",
                field_errors={"robustness_run_ids": "duplicates"},
            )

        manifests: dict[str, dict[str, Any]] = {}
        checksums: dict[str, str] = {}
        seen_test_types: dict[str, str] = {}
        # Validate in caller order — do not sort first (sorting must not hide
        # duplicate test_type collisions).
        for robustness_id in robustness_run_ids:
            path = robustness_manifest_path(self.root, robustness_id)
            if not path.is_file():
                raise GateEvaluationError(
                    f"robustness manifest not found: {robustness_id}",
                    field_errors={"robustness_run_ids": f"missing: {robustness_id}"},
                )
            # Seal first — never trust measurements from an unsealed / tampered
            # post-completion manifest.
            digest = self._verify_robustness_manifest_seal(robustness_id)
            checksums[f"robustness/{robustness_id}/manifest.json"] = digest
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise GateEvaluationError(
                    f"robustness manifest is not an object: {robustness_id}",
                    field_errors={"robustness_run_ids": "invalid manifest"},
                )
            self._validate_robustness_manifest(
                raw,
                robustness_id=robustness_id,
                run_id=run_id,
                base_manifest=base_manifest,
            )
            test_type = str(raw.get("test_type") or "")
            if not test_type:
                raise GateEvaluationError(
                    f"robustness {robustness_id} is missing test_type",
                    field_errors={"robustness_run_ids": "missing test_type"},
                )
            prior = seen_test_types.get(test_type)
            if prior is not None:
                raise GateEvaluationError(
                    f"duplicate robustness test_type={test_type!r}: "
                    f"{prior} and {robustness_id} (refusing silent overwrite)",
                    field_errors={"robustness_run_ids": f"duplicate test_type={test_type}"},
                )
            seen_test_types[test_type] = robustness_id
            manifests[robustness_id] = raw
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
            robustness_run_ids,
            run_id=run_id,
            base_manifest=manifest,
        )

        measurements = _measurements_from_metrics(metrics)
        # Merge in deterministic test_type order so measurement keys are stable;
        # duplicate test_types were already rejected above.
        for robustness_id in sorted(
            robustness_manifests,
            key=lambda rid: str(robustness_manifests[rid].get("test_type") or rid),
        ):
            measurements.update(
                _measurements_from_robustness_manifest(
                    self.registry,
                    robustness_manifests[robustness_id],
                    robustness_id=robustness_id,
                    base_run_id=run_id,
                )
            )

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
            evaluation_code_commit = _resolve_evaluation_code_commit(self.repo_root)
        except ValueError as exc:
            raise GateEvaluationError(
                f"evaluation_code_commit could not be resolved: {exc}",
                field_errors={"evaluation_code_commit": str(exc)},
            ) from exc

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
