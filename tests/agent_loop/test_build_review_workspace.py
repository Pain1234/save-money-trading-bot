"""Unit tests for build_review_workspace allowlist / deny / git-blob isolation."""

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


def _git_init_with_file(repo: Path, rel: str, content: str) -> str:
    """Create a tiny git repo with one committed file; return HEAD SHA."""
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return sha


def _run_build(
    *,
    repo_root: Path,
    diff: Path,
    out_dir: Path,
    git_rev: str,
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
            "--git-rev",
            git_rev,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_allowlisted_file_copied_from_git_blob(tmp_path):
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "src/ok.py", "print('ok')\n")
    # Dirty worktree must NOT be used
    (repo / "src" / "ok.py").write_text("print('DIRTY')\n", encoding="utf-8")
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
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    copied = (out / "src" / "ok.py").read_text(encoding="utf-8")
    assert "DIRTY" not in copied
    assert "print('ok')" in copied
    manifest = json.loads((out / "workspace-manifest.json").read_text(encoding="utf-8"))
    assert "src/ok.py" in manifest["allowlisted"]
    assert manifest["git_rev"] == sha
    assert "repo_root" not in manifest
    assert (out / "codex-review-prompt.md").is_file()
    assert (out / "current-diff.patch").is_file()


def test_env_in_diff_fail_closed(tmp_path):
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "ok.py", "x=1\n")
    diff = tmp_path / "env.diff"
    diff.write_text(
        "diff --git a/.env b/.env\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -0,0 +1 @@\n"
        "+SECRET=should-not-reach-codex\n"
        "diff --git a/ok.py b/ok.py\n"
        "--- a/ok.py\n"
        "+++ b/ok.py\n"
        "@@ -1 +1 @@\n"
        "+x=1\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "SECRET=should-not-reach-codex" not in (proc.stderr or "")
    assert "deny-listed" in (proc.stderr or "").lower() or "DENIED" in (proc.stderr or "")
    assert not out.exists() or not any(out.rglob("*"))


def test_codex_dir_in_diff_fail_closed(tmp_path):
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "ok.py", "x=1\n")
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
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists() or not (out / ".codex").exists()


def test_symlink_blob_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # Create a git symlink (mode 120000)
    link = repo / "link.py"
    link.write_text(".env\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # Convert to symlink in index
    subprocess.run(
        ["git", "update-index", "--chmod=+x", "link.py"],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    # Proper symlink via hash-object / update-index
    subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input=b".env",
        check=True,
        capture_output=True,
    )
    # Use git mklink approach: write symlink with update-index --cacheinfo
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input=b".env",
        capture_output=True,
        check=True,
    ).stdout.decode().strip()
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"120000,{blob},link.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "symlink"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    diff = tmp_path / "link.diff"
    diff.write_text(
        "diff --git a/link.py b/link.py\n"
        "--- a/link.py\n"
        "+++ b/link.py\n"
        "@@ -0,0 +1 @@\n"
        "+.env\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "symlink" in (proc.stderr or "").lower()


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


def test_paths_from_diff_extracts_c_quoted_paths():
    spec = importlib.util.spec_from_file_location(
        "build_review_workspace_quoted", BUILD_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    diff = (
        'diff --git "a/foo bar.py" "b/foo bar.py"\n'
        '--- "a/foo bar.py"\n'
        '+++ "b/foo bar.py"\n'
        "@@ -1 +1 @@\n"
        "+x\n"
        '--- "a/foo\\tbar"\n'
        '+++ "b/foo\\tbar"\n'
    )
    paths = mod.paths_from_diff(diff)
    assert "foo bar.py" in paths
    assert "foo\tbar" in paths
    assert mod.decode_c_quoted_path(r'b/foo\tbar') == "b/foo\tbar"
    assert mod.decode_c_quoted_path(r'b/foo\"bar') == 'b/foo"bar'


def test_quoted_deny_path_in_diff_fail_closed(tmp_path):
    """C-quoted path with space matching deny must fail closed (exit 1)."""
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "ok.py", "x=1\n")
    diff = tmp_path / "quoted_secret.diff"
    diff.write_text(
        'diff --git "a/foo secret/token.txt" "b/foo secret/token.txt"\n'
        '--- "a/foo secret/token.txt"\n'
        '+++ "b/foo secret/token.txt"\n'
        "@@ -0,0 +1 @@\n"
        "+leak\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "deny-listed" in (proc.stderr or "").lower() or "DENIED" in (proc.stderr or "")
    assert not out.exists() or not any(out.rglob("*"))


def test_agents_md_from_git_blob_not_worktree(tmp_path):
    """Dirty worktree AGENTS.md must not override the committed blob."""
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "AGENTS.md", "COMMITTED_AGENTS\n")
    # Also need a diff path so workspace build has something besides agents
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add ok"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "AGENTS.md").write_text("DIRTY_WORKTREE_AGENTS\n", encoding="utf-8")
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
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    agents = (out / "AGENTS.md").read_text(encoding="utf-8")
    assert "COMMITTED_AGENTS" in agents
    assert "DIRTY_WORKTREE" not in agents


def test_gate_helpers_module_importable():
    """Regression: helpers must not live under ambiguous `conftest` name."""
    import gate_helpers

    assert hasattr(gate_helpers, "discover_powershell")
    assert hasattr(gate_helpers, "run_gate")
    assert hasattr(gate_helpers, "REPO_ROOT")
