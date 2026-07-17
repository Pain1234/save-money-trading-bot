"""Fail-closed cost_model_version registration (#206 / Codex F1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.__main__ import _cost_model_version_from_run
from research.costs import COST_MODEL_VERSION


def _write(run_dir: Path, *, costs, manifest) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    if costs is not None:
        (run_dir / "costs.json").write_text(
            json.dumps(costs), encoding="utf-8"
        )
    if manifest is not None:
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )


def test_registration_version_requires_both_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        costs={"cost_model_version": COST_MODEL_VERSION},
        manifest=None,
    )
    with pytest.raises(ValueError, match="missing run_manifest"):
        _cost_model_version_from_run(run_dir)


def test_registration_version_requires_costs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        costs=None,
        manifest={"cost_model_version": COST_MODEL_VERSION},
    )
    with pytest.raises(ValueError, match="missing costs"):
        _cost_model_version_from_run(run_dir)


def test_registration_version_rejects_empty(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        costs={"cost_model_version": "   "},
        manifest={"cost_model_version": COST_MODEL_VERSION},
    )
    with pytest.raises(ValueError, match="non-empty string"):
        _cost_model_version_from_run(run_dir)


def test_registration_version_rejects_non_string(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        costs={"cost_model_version": 1.1},
        manifest={"cost_model_version": COST_MODEL_VERSION},
    )
    with pytest.raises(ValueError, match="non-empty string"):
        _cost_model_version_from_run(run_dir)


def test_registration_version_rejects_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        costs={"cost_model_version": "1.1"},
        manifest={"cost_model_version": "1.0"},
    )
    with pytest.raises(ValueError, match="mismatch"):
        _cost_model_version_from_run(run_dir)


def test_registration_version_agreeing_pair(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        costs={"cost_model_version": COST_MODEL_VERSION},
        manifest={"cost_model_version": COST_MODEL_VERSION},
    )
    assert _cost_model_version_from_run(run_dir) == COST_MODEL_VERSION
