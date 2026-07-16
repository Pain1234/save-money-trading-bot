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
    assert mod.is_denied("auth.json")
    assert mod.is_denied("nested/auth.json")
    assert mod.is_denied("id_ed25519")
    assert mod.is_denied("id_ed25519.pub")
    assert mod.is_denied("id_ed25519_backup")
    assert mod.is_denied("id_rsa.old")
    assert mod.is_denied("ID_ED25519_BACKUP")
    assert mod.is_denied("keys/id_dsa_2025")
    assert mod.is_denied(r"keys\id_rsa_backup")
    assert mod.is_denied("foo.keystore")
    assert mod.is_denied("tls.pem")
    assert not mod.is_denied("src/ok.py")


def test_private_key_basename_and_rename_denylist(tmp_path):
    """id_ed25519_backup / id_rsa.old / case / rename from&to all fail closed."""
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "ok.py", "x=1\n")
    cases = [
        (
            "backup.diff",
            "diff --git a/id_ed25519_backup b/id_ed25519_backup\n"
            "--- a/id_ed25519_backup\n"
            "+++ b/id_ed25519_backup\n"
            "@@ -0,0 +1 @@\n"
            "+ssh-key\n",
        ),
        (
            "rsa_old.diff",
            "diff --git a/id_rsa.old b/id_rsa.old\n"
            "--- a/id_rsa.old\n"
            "+++ b/id_rsa.old\n"
            "@@ -0,0 +1 @@\n"
            "+ssh-key\n",
        ),
        (
            "case.diff",
            "diff --git a/ID_ED25519_BACKUP b/ID_ED25519_BACKUP\n"
            "--- a/ID_ED25519_BACKUP\n"
            "+++ b/ID_ED25519_BACKUP\n"
            "@@ -0,0 +1 @@\n"
            "+ssh-key\n",
        ),
        (
            "rename_to.diff",
            "diff --git a/ok.py b/id_ed25519_backup\n"
            "similarity index 100%\n"
            "rename from ok.py\n"
            "rename to id_ed25519_backup\n",
        ),
        (
            "rename_from.diff",
            "diff --git a/id_rsa.old b/ok.py\n"
            "similarity index 100%\n"
            "rename from id_rsa.old\n"
            "rename to ok.py\n",
        ),
    ]
    for name, body in cases:
        diff = tmp_path / name
        diff.write_text(body, encoding="utf-8")
        out = tmp_path / f"ws-{name}"
        proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
        assert proc.returncode == 1, name + (proc.stdout or "") + (proc.stderr or "")
        assert "deny-listed" in (proc.stderr or "").lower() or "DENIED" in (proc.stderr or "")


def test_private_key_header_in_diff_and_blob_fail_closed(tmp_path):
    """PEM private key header in diff/blob → PermissionError; no key body in logs."""
    import secret_fragments as sf

    repo = tmp_path / "repo"
    key_body = (
        sf.private_key_begin("OPENSSH")
        + "\n"
        + "SUPER_SECRET_KEY_MATERIAL_DO_NOT_LOG\n"
        + sf.private_key_end("OPENSSH")
        + "\n"
    )
    sha = _git_init_with_file(repo, "notes.txt", key_body)
    diff = tmp_path / "pem.diff"
    diff.write_text(
        "diff --git a/notes.txt b/notes.txt\n"
        "--- a/notes.txt\n"
        "+++ b/notes.txt\n"
        "@@ -0,0 +1,3 @@\n"
        "+"
        + sf.private_key_begin("OPENSSH")
        + "\n"
        "+SUPER_SECRET_KEY_MATERIAL_DO_NOT_LOG\n"
        "+"
        + sf.private_key_end("OPENSSH")
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    err = proc.stderr or ""
    assert "private key header" in err.lower() or "DENIED" in err
    assert "SUPER_SECRET_KEY_MATERIAL_DO_NOT_LOG" not in err
    assert "SUPER_SECRET_KEY_MATERIAL_DO_NOT_LOG" not in (proc.stdout or "")


def test_private_key_header_in_blob_only(tmp_path):
    """Committed blob with PEM header fails even if diff hunk omits the header line."""
    import secret_fragments as sf

    repo = tmp_path / "repo"
    key_body = (
        sf.private_key_begin("RSA")
        + "\n"
        + "BLOB_SECRET_MATERIAL\n"
        + sf.private_key_end("RSA")
        + "\n"
    )
    sha = _git_init_with_file(repo, "legacy.txt", key_body)
    diff = tmp_path / "touch.diff"
    # Diff mentions the path but added lines have no header (still load blob).
    diff.write_text(
        "diff --git a/legacy.txt b/legacy.txt\n"
        "--- a/legacy.txt\n"
        "+++ b/legacy.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " "
        + sf.private_key_begin("RSA")
        + "\n"
        "-BLOB_SECRET_MATERIAL\n"
        "+BLOB_SECRET_MATERIAL\n"
        " "
        + sf.private_key_end("RSA")
        + "\n",
        encoding="utf-8",
    )
    # The + line is not a header; context lines are not scanned as additions.
    # Blob load must still catch the header.
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    err = proc.stderr or ""
    assert (
        "private key header detected in path" in err.lower()
        or "private key header" in err.lower()
    )
    assert "BLOB_SECRET_MATERIAL" not in err


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
    # Octal escapes are UTF-8 bytes: \303\266 → ö
    assert "föo" in mod.decode_c_quoted_path(r"b/f\303\266o.txt")
    assert mod.decode_c_quoted_path(r"b/f\303\266o.txt").endswith("föo.txt")


def test_paths_from_diff_binary_and_rename_headers():
    spec = importlib.util.spec_from_file_location(
        "build_review_workspace_binary", BUILD_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    binary_diff = (
        "diff --git a/.env b/.env\n"
        "Binary files a/.env and b/.env differ\n"
    )
    paths = mod.paths_from_diff(binary_diff)
    assert ".env" in paths

    rename_diff = (
        "diff --git a/ok.py b/.env\n"
        "similarity index 100%\n"
        "rename from ok.py\n"
        "rename to .env\n"
    )
    rpaths = mod.paths_from_diff(rename_diff)
    assert "ok.py" in rpaths
    assert ".env" in rpaths

    copy_diff = (
        "diff --git a/src/a.py b/credentials.json\n"
        "copy from src/a.py\n"
        "copy to credentials.json\n"
    )
    cpaths = mod.paths_from_diff(copy_diff)
    assert "src/a.py" in cpaths
    assert "credentials.json" in cpaths


def test_binary_env_diff_fail_closed(tmp_path):
    """Binary .env diff must fail closed even without ---/+++ hunks."""
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "src/ok.py", "x=1\n")
    diff = tmp_path / "binary_env.diff"
    diff.write_text(
        "diff --git a/.env b/.env\n"
        "Binary files a/.env and b/.env differ\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "deny-listed" in (proc.stderr or "").lower() or "DENIED" in (proc.stderr or "")
    assert not out.exists() or not any(out.rglob("*"))


def test_rename_to_denied_path_fail_closed(tmp_path):
    """rename to a deny-listed path must fail closed."""
    repo = tmp_path / "repo"
    sha = _git_init_with_file(repo, "ok.py", "x=1\n")
    diff = tmp_path / "rename_env.diff"
    diff.write_text(
        "diff --git a/ok.py b/.env\n"
        "similarity index 100%\n"
        "rename from ok.py\n"
        "rename to .env\n",
        encoding="utf-8",
    )
    out = tmp_path / "ws"
    proc = _run_build(repo_root=repo, diff=diff, out_dir=out, git_rev=sha)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "deny-listed" in (proc.stderr or "").lower() or "DENIED" in (proc.stderr or "")
    assert not out.exists() or not any(out.rglob("*"))


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
