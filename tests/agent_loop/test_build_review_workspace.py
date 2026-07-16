"""Unit tests for build_review_workspace allowlist / deny isolation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / ".agent-loop" / "build_review_workspace.py"
PROMPT = REPO_ROOT / ".agent-loop" / "codex-review-prompt.md"
SCHEMA = REPO_ROOT / ".agent-loop" / "codex-review-schema.json"


def _run_build(
    *,
    repo_root: Path,
    diff: Path,
    out_dir: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--repo-root",
            str(repo_root),
            "--diff",
            str(diff),
            "--out-dir",
            str(out_dir),
            "--prompt",
            str(PROMPT),
            "--schema",
            str(SCHEMA),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_allowlisted_file_copied(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src" / "ok.py"
    src.parent.mkdir(parents=True)
    src.write_text("print('ok')\n", encoding="utf-8")
    diff = tmp_path / "ok.diff"
    diff.write_text(
        "diff --git a/src/ok.py b/src/ok.py\n"
        "--- a/src/ok.py\n"
        "+++ b/src/ok.py\n"
        "@@ -1 +1 @@\n"
        "+print('ok')\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "src" / "ok.py").is_file()
    manifest = json.loads((out / "workspace-manifest.json").read_text(encoding="utf-8"))
    assert "src/ok.py" in manifest["allowlisted"]
    assert (out / "codex-review-prompt.md").is_file()
    assert (out / "current-diff.patch").is_file()


def test_env_denied_even_if_in_diff(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env_file = repo / ".env"
    env_file.write_text("SECRET=should-not-copy\n", encoding="utf-8")
    ok = repo / "ok.py"
    ok.write_text("x=1\n", encoding="utf-8")
    diff = tmp_path / "env.diff"
    diff.write_text(
        "diff --git a/.env b/.env\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -0,0 +1 @@\n"
        "+SECRET=should-not-copy\n"
        "diff --git a/ok.py b/ok.py\n"
        "--- a/ok.py\n"
        "+++ b/ok.py\n"
        "@@ -1 +1 @@\n"
        "+x=1\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (out / ".env").exists()
    assert (out / "ok.py").is_file()
    manifest = json.loads((out / "workspace-manifest.json").read_text(encoding="utf-8"))
    assert ".env" in manifest["denied"]
    assert "ok.py" in manifest["allowlisted"]


def test_codex_dir_denied(tmp_path):
    repo = tmp_path / "repo"
    codex_dir = repo / ".codex"
    codex_dir.mkdir(parents=True)
    secret = codex_dir / "foo.json"
    secret.write_text('{"token":"nope"}\n', encoding="utf-8")
    diff = tmp_path / "codex.diff"
    diff.write_text(
        "diff --git a/.codex/foo.json b/.codex/foo.json\n"
        "--- a/.codex/foo.json\n"
        "+++ b/.codex/foo.json\n"
        "@@ -0,0 +1 @@\n"
        '+{"token":"nope"}\n',
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (out / ".codex").exists()
    manifest = json.loads((out / "workspace-manifest.json").read_text(encoding="utf-8"))
    assert any(p.startswith(".codex") for p in manifest["denied"])


def test_is_denied_helpers():
    spec = importlib.util.spec_from_file_location(
        "build_review_workspace_gate", BUILD_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.is_denied(".env")
    assert mod.is_denied(".env.local")
    assert mod.is_denied(".codex/foo")
    assert mod.is_denied("path/with/secret/token.txt")
    assert mod.is_denied("credentials.json")
    assert not mod.is_denied("src/ok.py")
