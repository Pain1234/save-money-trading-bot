"""Fail-closed git provenance for research runs (#207)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from research.runner import RunRequest, resolve_git_commit, run_experiment

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


def test_resolve_git_commit_clean_returns_sha() -> None:
    sha = resolve_git_commit(REPO_ROOT, allow_dirty=True)
    assert len(sha) >= 7
    assert sha.lower() != "unknown"


def test_resolve_git_commit_missing_head_fails() -> None:
    with patch("research.runner.subprocess.check_output", side_effect=FileNotFoundError):
        with pytest.raises(ValueError, match="cannot read HEAD"):
            resolve_git_commit(REPO_ROOT, allow_dirty=False)


def test_resolve_git_commit_dirty_fails_closed() -> None:
    def _fake_check_output(cmd: list[str], **_kwargs: object) -> str:
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return "abc123deadbeef\n"
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return " M services/research/runner.py\n"
        raise AssertionError(cmd)

    with patch("research.runner.subprocess.check_output", side_effect=_fake_check_output):
        with pytest.raises(ValueError, match="working tree is dirty"):
            resolve_git_commit(REPO_ROOT, allow_dirty=False)


def test_resolve_git_commit_dirty_allowed() -> None:
    def _fake_check_output(cmd: list[str], **_kwargs: object) -> str:
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return "abc123deadbeef\n"
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return " M services/research/runner.py\n"
        raise AssertionError(cmd)

    with patch("research.runner.subprocess.check_output", side_effect=_fake_check_output):
        assert resolve_git_commit(REPO_ROOT, allow_dirty=True) == "abc123deadbeef"


def test_run_experiment_fails_closed_when_git_unknown(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    with patch(
        "research.runner.resolve_git_commit",
        side_effect=ValueError("git provenance unavailable: cannot read HEAD"),
    ):
        outcome = run_experiment(
            RunRequest(
                spec=spec,
                bundle=bundle,
                artifacts_root=tmp_path / "out",
                repo_root=REPO_ROOT,
            )
        )
    assert outcome.status == "failed"
    assert outcome.artifact_path is None
    assert "git provenance" in (outcome.error or "")


def test_run_experiment_allow_dirty_git_completes(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    with patch("research.runner.resolve_git_commit", return_value="deadbeef"):
        outcome = run_experiment(
            RunRequest(
                spec=spec,
                bundle=bundle,
                artifacts_root=tmp_path / "out",
                repo_root=REPO_ROOT,
                allow_dirty_git=True,
            )
        )
    assert outcome.status == "complete", outcome.error
    assert outcome.artifact_path is not None
    import json

    manifest = json.loads(
        (outcome.artifact_path / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["git_commit"] == "deadbeef"
