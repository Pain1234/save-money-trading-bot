"""Real double-run semantic artifact gate (#146)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from research.identity import semantic_artifact_hash
from research.repro import compare_semantic_run_dirs, semantic_manifest_from_file
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


def test_double_run_semantic_hashes_match(tmp_path: Path) -> None:
    """Two runs, different artifacts_root → same semantic metrics/trades hashes."""
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"

    out_a = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=root_a,
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    out_b = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=root_b,
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert out_a.status == "complete", out_a.error
    assert out_b.status == "complete", out_b.error
    assert out_a.run_id == out_b.run_id
    assert out_a.attempt_id != out_b.attempt_id
    assert out_a.artifact_path is not None
    assert out_b.artifact_path is not None

    hashes = compare_semantic_run_dirs(out_a.artifact_path, out_b.artifact_path)
    assert "metrics.json" in hashes
    assert "trades.json" in hashes

    regime_a = json.loads(
        (out_a.artifact_path / "regime_labels.json").read_text(encoding="utf-8")
    )
    regime_b = json.loads(
        (out_b.artifact_path / "regime_labels.json").read_text(encoding="utf-8")
    )
    assert regime_a == regime_b
    assert regime_a["classifier_version"] == "1.0"

    m_a = json.loads(
        (out_a.artifact_path / "run_manifest.json").read_text(encoding="utf-8")
    )
    m_b = json.loads(
        (out_b.artifact_path / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert m_a["attempt_id"] != m_b["attempt_id"]
    assert semantic_artifact_hash(
        semantic_manifest_from_file(out_a.artifact_path / "run_manifest.json")
    ) == semantic_artifact_hash(
        semantic_manifest_from_file(out_b.artifact_path / "run_manifest.json")
    )


def test_same_root_second_run_refuses_overwrite(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    first = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert first.status == "complete", first.error
    second = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert second.status == "failed"
    assert second.error is not None
    assert "overwrite" in second.error.lower() or "exists" in second.error.lower()


def test_compare_detects_divergence(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    out = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "ok",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert out.status == "complete" and out.artifact_path is not None
    twin = tmp_path / "tampered"
    twin.mkdir(parents=True)
    for name in (
        "metrics.json",
        "trades.json",
        "equity.json",
        "costs.json",
        "experiment.json",
        "run_manifest.json",
        "chart_data.json",
    ):
        (twin / name).write_bytes((out.artifact_path / name).read_bytes())
    metrics = json.loads((twin / "metrics.json").read_text(encoding="utf-8"))
    metrics["net_pnl"] = "999999"
    (twin / "metrics.json").write_text(
        json.dumps(metrics, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="semantic hash mismatch"):
        compare_semantic_run_dirs(out.artifact_path, twin)
