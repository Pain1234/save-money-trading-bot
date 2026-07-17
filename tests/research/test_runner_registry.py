"""Tests for research runner, artifacts, and registry (#143/#145)."""

from __future__ import annotations

from pathlib import Path

from research.artifacts import load_checksums, verify_checksums
from research.registry import ExperimentRegistry
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


def test_dry_run_identity(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
            dry_run=True,
                    allow_dirty_git=True,
        )
    )
    assert outcome.status == "dry_run"
    assert outcome.run_id.startswith("run_")


def test_run_writes_artifacts_and_registry(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    out_root = tmp_path / "out"
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=out_root,
            repo_root=REPO_ROOT,
            dry_run=False,
                    allow_dirty_git=True,
        )
    )
    assert outcome.status == "complete", outcome.error
    assert outcome.artifact_path is not None
    run_dir = outcome.artifact_path
    for name in (
        "experiment.json",
        "run_manifest.json",
        "metrics.json",
        "report.md",
        "trades.json",
        "equity.json",
        "events.jsonl",
        "checksums.json",
        "costs.json",
    ):
        assert (run_dir / name).is_file(), name
    import json

    costs = json.loads((run_dir / "costs.json").read_text(encoding="utf-8"))
    assert costs["gross_net_required"] is True
    assert "fee_model_version" in costs
    verify_checksums(run_dir)

    again = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=out_root,
            repo_root=REPO_ROOT,
                    allow_dirty_git=True,
        )
    )
    assert again.status == "failed"
    assert again.error is not None

    registry = ExperimentRegistry(out_root)
    registry.register_complete(
        experiment_id=outcome.experiment_id,
        run_id=outcome.run_id,
        attempt_id=outcome.attempt_id,
        strategy_version=spec.strategy_version,
        dataset_version=spec.dataset_manifest_ref.dataset_id,
        cost_model_version="1.0",
        benchmark_ref=spec.benchmark,
        artifact_path=run_dir,
        checksums=load_checksums(run_dir),
    )
    listed = registry.list_entries()
    assert len(listed) == 1
    assert listed[0].run_id == outcome.run_id

    sidecar = registry.invalidate(
        outcome.run_id,
        reason="fixture correction",
        actor="test",
    )
    assert sidecar.is_file()
    manifest_bytes = (run_dir / "run_manifest.json").read_bytes()
    assert (run_dir / "run_manifest.json").read_bytes() == manifest_bytes
    assert registry.show(outcome.run_id).status == "invalidated"
