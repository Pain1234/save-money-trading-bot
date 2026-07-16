"""Adversarial dataset binding tests (#163)."""

from __future__ import annotations

from pathlib import Path

from research.dataset_binding import bind_dataset_to_bundle, hash_research_bundle
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import (
    REPO_ROOT,
    align_spec_to_bundle,
    btc_bundle,
    research_time_range,
)


def test_mismatched_bundle_rejected(tmp_path: Path) -> None:
    matching = btc_bundle(price="100")
    other = btc_bundle(price="200")
    spec = align_spec_to_bundle(tmp_path, matching)
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=other,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
        )
    )
    assert outcome.status == "failed"
    assert outcome.artifact_path is None
    assert outcome.error is not None
    assert "content_hash" in outcome.error.lower() or "does not match" in outcome.error


def test_same_declared_ref_different_bundles_no_shared_complete_run(
    tmp_path: Path,
) -> None:
    a = btc_bundle(price="100")
    b = btc_bundle(price="111")
    spec = align_spec_to_bundle(tmp_path, a)
    out_a = run_experiment(
        RunRequest(
            spec=spec,
            bundle=a,
            artifacts_root=tmp_path / "a",
            repo_root=REPO_ROOT,
        )
    )
    out_b = run_experiment(
        RunRequest(
            spec=spec,
            bundle=b,
            artifacts_root=tmp_path / "b",
            repo_root=REPO_ROOT,
        )
    )
    assert out_a.status == "complete", out_a.error
    assert out_b.status == "failed", out_b.error
    assert out_b.artifact_path is None


def test_bind_applies_time_range(tmp_path: Path) -> None:
    bundle = btc_bundle(end_day=28)
    spec = align_spec_to_bundle(tmp_path, bundle)
    _manifest, filtered, digest = bind_dataset_to_bundle(
        spec, bundle, repo_root=REPO_ROOT
    )
    assert digest == spec.dataset_manifest_ref.content_hash
    assert digest == hash_research_bundle(filtered, ("BTC",))
    tr = research_time_range()
    for c in filtered.daily["BTC"]:
        assert tr.start <= c.open_time <= tr.end
