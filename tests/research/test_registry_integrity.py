"""Registry integrity tests (#145)."""

from __future__ import annotations

from pathlib import Path

import pytest
from research.artifacts import load_checksums
from research.registry import ExperimentRegistry
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


def _complete_run(tmp_path: Path):
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "artifacts_root",
            repo_root=REPO_ROOT,
        )
    )
    assert outcome.status == "complete", outcome.error
    assert outcome.artifact_path is not None
    registry = ExperimentRegistry(tmp_path / "artifacts_root")
    registry.register_complete(
        experiment_id=outcome.experiment_id,
        run_id=outcome.run_id,
        attempt_id=outcome.attempt_id,
        strategy_version=spec.strategy_version,
        dataset_version=spec.dataset_manifest_ref.dataset_id,
        cost_model_version="1.0",
        benchmark_ref=spec.benchmark,
        artifact_path=outcome.artifact_path,
        checksums=load_checksums(outcome.artifact_path),
    )
    return registry, outcome, spec


def test_duplicate_complete_run_id_rejected(tmp_path: Path) -> None:
    registry, outcome, spec = _complete_run(tmp_path)
    with pytest.raises(ValueError, match="duplicate complete"):
        registry.register_complete(
            experiment_id=outcome.experiment_id,
            run_id=outcome.run_id,
            attempt_id="att_other",
            strategy_version=spec.strategy_version,
            dataset_version=spec.dataset_manifest_ref.dataset_id,
            cost_model_version="1.0",
            benchmark_ref=spec.benchmark,
            artifact_path=outcome.artifact_path,  # type: ignore[arg-type]
            checksums=load_checksums(outcome.artifact_path),  # type: ignore[arg-type]
        )


def test_compare_incompatible_inputs(tmp_path: Path) -> None:
    registry, outcome, spec = _complete_run(tmp_path)
    registry._append(  # noqa: SLF001 — test injects incompatible sibling
        {
            "experiment_id": outcome.experiment_id,
            "run_id": "run_other",
            "attempt_id": "att_x",
            "status": "complete",
            "strategy_version": "9.9.9",
            "dataset_version": spec.dataset_manifest_ref.dataset_id,
            "cost_model_version": "1.0",
            "benchmark_ref": spec.benchmark,
            "created_at": "2026-01-01T00:00:00.000000Z",
            "artifact_path": str(outcome.artifact_path),
            "checksums": load_checksums(outcome.artifact_path),  # type: ignore[arg-type]
        }
    )
    result = registry.compare(outcome.run_id, "run_other")
    assert result["compatible"] is False


def test_reconstruct_from_artifacts(tmp_path: Path) -> None:
    registry, outcome, _spec = _complete_run(tmp_path)
    rebuilt = registry.reconstruct_from_artifacts()
    assert any(e.run_id == outcome.run_id for e in rebuilt)


def test_checksum_mismatch_detected(tmp_path: Path) -> None:
    registry, outcome, _spec = _complete_run(tmp_path)
    assert outcome.artifact_path is not None
    metrics = outcome.artifact_path / "metrics.json"
    metrics.write_text(metrics.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        registry.show(outcome.run_id, verify=True)
