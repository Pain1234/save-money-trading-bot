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
