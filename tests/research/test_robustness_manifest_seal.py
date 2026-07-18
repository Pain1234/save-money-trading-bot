"""Trust-anchor tests for sealed robustness manifests (Issue #247 / #248 P1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from research.robustness import (
    ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
    RobustnessChildResult,
    RobustnessManifest,
    robustness_manifest_path,
    save_robustness_manifest,
    verify_robustness_manifest_seal,
)


def _minimal_manifest(robustness_id: str = "rob_seal_test") -> RobustnessManifest:
    return RobustnessManifest(
        schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
        robustness_id=robustness_id,
        test_type="bootstrap",
        base_experiment_id="exp_x",
        base_run_id="run_x",
        dataset_catalog_id=None,
        config={"seed": 1},
        created_at="2024-01-01T00:00:00.000000Z",
        children=(
            RobustnessChildResult(
                child_id="bootstrap_source",
                label="base",
                experiment_id="exp_x",
                run_id="run_x",
                status="complete",
            ),
        ),
        bootstrap_result={"net_pnl_quantiles": {"q05": "-1"}},
        summary={"n_children": 1, "n_complete": 1, "n_failed": 0},
    )


def test_save_writes_sidecar_and_verify_ok(tmp_path: Path) -> None:
    path, digest = save_robustness_manifest(tmp_path, _minimal_manifest())
    assert path.is_file()
    assert (path.parent / "manifest.json.sha256").read_text(encoding="utf-8").strip() == digest
    assert verify_robustness_manifest_seal(tmp_path, "rob_seal_test") == digest
    assert (
        verify_robustness_manifest_seal(
            tmp_path, "rob_seal_test", expected_hash=digest
        )
        == digest
    )


def test_tampered_manifest_fails_seal_verify(tmp_path: Path) -> None:
    _path, digest = save_robustness_manifest(tmp_path, _minimal_manifest())
    path = robustness_manifest_path(tmp_path, "rob_seal_test")
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"-1"', '"999"'), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_robustness_manifest_seal(
            tmp_path, "rob_seal_test", expected_hash=digest
        )


def test_get_manifest_redacts_measurements_when_seal_breaks(tmp_path: Path) -> None:
    """API/UI must not serve tampered completed measurements as trusted."""
    from research.robustness_jobs import RobustnessJob, RobustnessJobStore
    from research.robustness_service import RobustnessOrchestrationService

    _path, digest = save_robustness_manifest(tmp_path, _minimal_manifest())
    RobustnessJobStore(tmp_path).save(
        RobustnessJob(
            robustness_id="rob_seal_test",
            base_experiment_id="exp",
            base_run_id="run",
            test_type="walk_forward",
            status="completed",
            created_at="2024-01-01T00:00:00.000000Z",
            updated_at="2024-01-01T00:00:00.000000Z",
            finished_at="2024-01-01T00:00:00.000000Z",
            manifest_content_hash=digest,
        )
    )
    svc = RobustnessOrchestrationService(tmp_path, repo_root=tmp_path, allow_dirty_git=True)
    ok = svc.get_manifest("rob_seal_test")
    assert ok is not None
    assert ok["manifest_integrity"]["ok"] is True
    assert "children" in ok

    path = robustness_manifest_path(tmp_path, "rob_seal_test")
    path.write_text(
        path.read_text(encoding="utf-8").replace('"-1"', '"999"'),
        encoding="utf-8",
    )
    # Attacker also rewrites sidecar so only the job hash remains the trust anchor.
    (path.parent / "manifest.json.sha256").write_text(
        __import__("hashlib").sha256(path.read_bytes()).hexdigest() + "\n",
        encoding="utf-8",
    )
    broken = svc.get_manifest("rob_seal_test")
    assert broken is not None
    assert broken["manifest_integrity"]["ok"] is False
    assert "children" not in broken
    assert "summary" not in broken
    assert "bootstrap_result" not in broken


def test_get_manifest_redacts_when_job_missing(tmp_path: Path) -> None:
    from research.robustness_service import RobustnessOrchestrationService

    save_robustness_manifest(tmp_path, _minimal_manifest())
    svc = RobustnessOrchestrationService(tmp_path, repo_root=tmp_path, allow_dirty_git=True)
    body = svc.get_manifest("rob_seal_test")
    assert body is not None
    assert body["manifest_integrity"]["ok"] is False
    assert "children" not in body
