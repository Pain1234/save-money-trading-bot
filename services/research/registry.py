"""Filesystem experiment registry and invalidation (Issue #145 / P4-05)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from research.artifacts import (
    compute_artifact_checksums,
    load_checksums,
    verify_checksums,
    verify_checksums_against,
)
from research.experiment_spec import load_experiment_spec
from research.identity import semantic_spec_dict
from research.run_manifest import load_run_manifest, semantic_manifest_payload

Status = Literal["complete", "failed", "invalidated"]


@dataclass(frozen=True)
class RegistryEntry:
    experiment_id: str
    run_id: str
    attempt_id: str
    status: Status
    strategy_version: str
    dataset_version: str
    cost_model_version: str
    benchmark_ref: str
    created_at: str
    artifact_path: str
    checksums: dict[str, str]


class ExperimentRegistry:
    """Local JSONL registry beside research artifacts."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "artifacts" / "research" / "registry.jsonl"
        self.invalidation_dir = root / "artifacts" / "research" / "invalidations"
        self.artifacts_root = root / "artifacts" / "research"

    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def register_complete(
        self,
        *,
        experiment_id: str,
        run_id: str,
        attempt_id: str,
        strategy_version: str,
        dataset_version: str,
        cost_model_version: str,
        benchmark_ref: str,
        artifact_path: Path,
        checksums: dict[str, str],
    ) -> None:
        if any(e.run_id == run_id and e.status == "complete" for e in self.list_entries()):
            msg = f"duplicate complete run_id forbidden: {run_id}"
            raise ValueError(msg)
        path = Path(artifact_path)
        on_disk = compute_artifact_checksums(path)
        if checksums != on_disk:
            msg = "provided checksums do not match finalized artifact set"
            raise ValueError(msg)
        # Helper seal must agree too when present.
        if (path / "checksums.json").is_file():
            seal = load_checksums(path)
            if seal != on_disk:
                msg = "checksums.json seal disagrees with artifact files"
                raise ValueError(msg)
        verify_checksums_against(path, checksums)
        self._append(
            {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "status": "complete",
                "strategy_version": strategy_version,
                "dataset_version": dataset_version,
                "cost_model_version": cost_model_version,
                "benchmark_ref": benchmark_ref,
                "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "artifact_path": str(artifact_path),
                "checksums": checksums,
            }
        )

    def list_entries(self) -> list[RegistryEntry]:
        if not self.path.exists():
            return []
        entries: list[RegistryEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            entries.append(
                RegistryEntry(
                    experiment_id=str(raw["experiment_id"]),
                    run_id=str(raw["run_id"]),
                    attempt_id=str(raw["attempt_id"]),
                    status=raw["status"],
                    strategy_version=str(raw["strategy_version"]),
                    dataset_version=str(raw["dataset_version"]),
                    cost_model_version=str(raw["cost_model_version"]),
                    benchmark_ref=str(raw["benchmark_ref"]),
                    created_at=str(raw["created_at"]),
                    artifact_path=str(raw["artifact_path"]),
                    checksums={str(k): str(v) for k, v in raw.get("checksums", {}).items()},
                )
            )
        return entries

    def _verify_entry_artifacts(self, entry: RegistryEntry) -> None:
        path = Path(entry.artifact_path)
        if not path.is_dir():
            msg = f"missing or deleted artifacts for {entry.run_id}: {path}"
            raise FileNotFoundError(msg)
        if not entry.checksums:
            msg = f"registry entry for {entry.run_id} has empty trusted checksums"
            raise ValueError(msg)
        # Trust anchor = append-only registry snapshot, not mutable checksums.json.
        verify_checksums_against(path, entry.checksums)

    def show(self, run_id: str, *, verify: bool = True) -> RegistryEntry:
        for entry in reversed(self.list_entries()):
            if entry.run_id == run_id:
                if verify and entry.status == "complete":
                    self._verify_entry_artifacts(entry)
                return entry
        msg = f"run_id not found: {run_id}"
        raise KeyError(msg)

    def invalidate(
        self,
        run_id: str,
        *,
        reason: str,
        actor: str,
        replacement_run_id: str | None = None,
    ) -> Path:
        """Append-only invalidation sidecar; does not mutate RunManifest."""
        entry = self.show(run_id, verify=False)
        if entry.status == "invalidated":
            msg = f"run already invalidated: {run_id}"
            raise ValueError(msg)
        self.invalidation_dir.mkdir(parents=True, exist_ok=True)
        sidecar = self.invalidation_dir / f"{run_id}.jsonl"
        record = {
            "run_id": run_id,
            "status": "invalidated",
            "reason": reason,
            "provenance": {
                "actor": actor,
                "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            },
            "replacement_run_id": replacement_run_id,
            "original_artifact_path": entry.artifact_path,
        }
        with sidecar.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._append(
            {
                "experiment_id": entry.experiment_id,
                "run_id": entry.run_id,
                "attempt_id": entry.attempt_id,
                "strategy_version": entry.strategy_version,
                "dataset_version": entry.dataset_version,
                "cost_model_version": entry.cost_model_version,
                "benchmark_ref": entry.benchmark_ref,
                "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "artifact_path": entry.artifact_path,
                "checksums": entry.checksums,
                "status": "invalidated",
                "invalidation_reason": reason,
                "replacement_run_id": replacement_run_id,
            }
        )
        return sidecar

    def compare(self, run_a: str, run_b: str) -> dict[str, Any]:
        a = self.show(run_a, verify=True)
        b = self.show(run_b, verify=True)
        diffs: dict[str, list[Any]] = {}

        def note(key: str, left: Any, right: Any) -> None:
            if left != right:
                diffs[key] = [left, right]

        note("status", a.status, b.status)
        note("strategy_version", a.strategy_version, b.strategy_version)
        note("dataset_version", a.dataset_version, b.dataset_version)
        note("cost_model_version", a.cost_model_version, b.cost_model_version)
        note("benchmark_ref", a.benchmark_ref, b.benchmark_ref)

        # Full semantic Spec + validated RunManifest identity (not a field subset).
        try:
            spec_a = load_experiment_spec(Path(a.artifact_path) / "experiment.json")
            spec_b = load_experiment_spec(Path(b.artifact_path) / "experiment.json")
            man_a = load_run_manifest(Path(a.artifact_path) / "run_manifest.json")
            man_b = load_run_manifest(Path(b.artifact_path) / "run_manifest.json")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return {
                "compatible": False,
                "a": a,
                "b": b,
                "diffs": {"artifact_load_error": [str(exc), None]},
            }

        sem_a = semantic_spec_dict(spec_a)
        sem_b = semantic_spec_dict(spec_b)
        for key in sorted(set(sem_a) | set(sem_b)):
            note(f"spec.{key}", sem_a.get(key), sem_b.get(key))

        man_sem_a = semantic_manifest_payload(man_a)
        man_sem_b = semantic_manifest_payload(man_b)
        for key in sorted(set(man_sem_a) | set(man_sem_b)):
            note(f"manifest.{key}", man_sem_a.get(key), man_sem_b.get(key))

        compatible = (
            a.status == "complete"
            and b.status == "complete"
            and not diffs
        )
        return {
            "compatible": compatible,
            "a": a,
            "b": b,
            "diffs": diffs,
        }

    def reconstruct_from_artifacts(self) -> list[RegistryEntry]:
        """Rebuild registry entries by scanning artifact directories.

        Does not mutate existing registry.jsonl; returns reconstructed complete runs.
        """
        if not self.artifacts_root.is_dir():
            return []
        rebuilt: list[RegistryEntry] = []
        for exp_dir in sorted(self.artifacts_root.iterdir()):
            if not exp_dir.is_dir() or exp_dir.name in {"invalidations"}:
                continue
            if exp_dir.name.endswith(".jsonl"):
                continue
            for run_dir in sorted(exp_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                manifest_path = run_dir / "run_manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    verify_checksums(run_dir)
                except (FileNotFoundError, ValueError):
                    continue
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                experiment = json.loads((run_dir / "experiment.json").read_text(encoding="utf-8"))
                costs_path = run_dir / "costs.json"
                cost_ver = "1.0"
                if costs_path.is_file():
                    costs = json.loads(costs_path.read_text(encoding="utf-8"))
                    cost_ver = str(costs.get("cost_model_version", "1.0"))
                rebuilt.append(
                    RegistryEntry(
                        experiment_id=str(manifest["experiment_id"]),
                        run_id=str(manifest["run_id"]),
                        attempt_id=str(manifest["attempt_id"]),
                        status="complete"
                        if manifest.get("status") == "complete"
                        else "failed",
                        strategy_version=str(manifest.get("strategy_version", "")),
                        dataset_version=str(
                            experiment.get("dataset_manifest_ref", {}).get("dataset_id", "")
                        ),
                        cost_model_version=cost_ver,
                        benchmark_ref=str(experiment.get("benchmark", "")),
                        created_at=str(manifest.get("created_at_utc", "")),
                        artifact_path=str(run_dir),
                        checksums=load_checksums(run_dir),
                    )
                )
        return rebuilt
