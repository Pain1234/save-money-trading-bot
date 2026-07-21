"""Registry integrity tests (#145)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from research.artifacts import load_checksums
from research.registry import ExperimentRegistry
from research.runner import RunRequest, run_experiment
from research.service import ResearchReadService

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
            allow_dirty_git=True,
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


def test_invalidation_sidecar_remains_authoritative_after_raw_complete_append(
    tmp_path: Path,
) -> None:
    registry, outcome, _spec = _complete_run(tmp_path)
    original = registry.show(outcome.run_id)
    registry.invalidate(outcome.run_id, reason="bad evidence", actor="test")

    reactivation = {
        **original.__dict__,
        "status": "complete",
        "created_at": "2099-01-01T00:00:00.000000Z",
    }
    with registry.path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(reactivation, sort_keys=True) + "\n")

    assert registry.show(outcome.run_id, verify=False).status == "invalidated"
    assert registry.list_entries()[-1].status == "invalidated"

    service = ResearchReadService(registry.root)
    assert service.get_entry(outcome.experiment_id).status == "invalidated"
    assert service.latest_entries()[0].status == "invalidated"


def test_invalidation_sidecar_blocks_all_complete_append_paths(tmp_path: Path) -> None:
    registry, outcome, spec = _complete_run(tmp_path)
    original = registry.show(outcome.run_id)
    registry.invalidate(outcome.run_id, reason="bad evidence", actor="test")

    with pytest.raises(ValueError, match="reactivation forbidden"):
        registry._append(  # noqa: SLF001 — exercises the central append guard
            {
                **original.__dict__,
                "status": "complete",
                "created_at": "2099-01-01T00:00:00.000000Z",
            }
        )

    with pytest.raises(ValueError, match="reactivation forbidden"):
        registry.register_complete(
            experiment_id=outcome.experiment_id,
            run_id=outcome.run_id,
            attempt_id=outcome.attempt_id,
            strategy_version=spec.strategy_version,
            dataset_version=spec.dataset_manifest_ref.dataset_id,
            cost_model_version="1.0",
            benchmark_ref=spec.benchmark,
            artifact_path=outcome.artifact_path,  # type: ignore[arg-type]
            checksums=load_checksums(outcome.artifact_path),  # type: ignore[arg-type]
        )


def test_reconstruct_preserves_invalidated_status_while_sidecar_exists(
    tmp_path: Path,
) -> None:
    registry, outcome, _spec = _complete_run(tmp_path)
    registry.invalidate(outcome.run_id, reason="bad evidence", actor="test")

    rebuilt = {
        entry.run_id: entry for entry in registry.reconstruct_from_artifacts()
    }

    assert rebuilt[outcome.run_id].status == "invalidated"


def test_checksum_mismatch_detected(tmp_path: Path) -> None:
    registry, outcome, _spec = _complete_run(tmp_path)
    assert outcome.artifact_path is not None
    metrics = outcome.artifact_path / "metrics.json"
    metrics.write_text(metrics.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        registry.show(outcome.run_id, verify=True)


def test_resealed_checksums_json_still_fails_against_registry(
    tmp_path: Path,
) -> None:
    """Mutate metrics.json and rewrite checksums.json — registry trust must fail."""
    from research.artifacts import compute_artifact_checksums

    registry, outcome, _spec = _complete_run(tmp_path)
    assert outcome.artifact_path is not None
    metrics = outcome.artifact_path / "metrics.json"
    metrics.write_text(metrics.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    # Reseal helper file so on-disk verify_checksums would pass.
    new_seal = compute_artifact_checksums(outcome.artifact_path)
    import json

    (outcome.artifact_path / "checksums.json").write_text(
        json.dumps(new_seal, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="trusted snapshot|checksum mismatch"):
        registry.show(outcome.run_id, verify=True)
