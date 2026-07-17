"""Fail-closed git provenance for research runs (#207)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from research.runner import resolve_git_commit


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(
        ["git", "config", "user.name", "test"],
        cwd=path,
        stdout=subprocess.DEVNULL,
    )
    (path / "README").write_text("x\\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "README"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "commit", "-m", "init"],
        cwd=path,
        stdout=subprocess.DEVNULL,
    )


def test_resolve_git_commit_clean(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sha = resolve_git_commit(tmp_path, allow_dirty=False)
    assert len(sha) >= 40
    assert sha.lower() != "unknown"


def test_resolve_git_commit_dirty_fails(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "extra.txt").write_text("dirty\\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dirty"):
        resolve_git_commit(tmp_path, allow_dirty=False)


def test_resolve_git_commit_dirty_allowed(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "extra.txt").write_text("dirty\\n", encoding="utf-8")
    sha = resolve_git_commit(tmp_path, allow_dirty=True)
    assert len(sha) >= 40


def test_resolve_git_commit_missing_repo_fails(tmp_path: Path) -> None:
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    with pytest.raises(ValueError, match="unable to resolve HEAD"):
        resolve_git_commit(empty, allow_dirty=False)
