"""Integration tests for run-codex-review.ps1 gate."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import secret_fragments as sf
from gate_helpers import discover_powershell, run_gate


def _result_path(repo_root: Path) -> Path:
    return repo_root / ".agent-loop" / "codex-review-result.json"


def _read_verdict(repo_root: Path) -> str:
    data = json.loads(_result_path(repo_root).read_text(encoding="utf-8"))
    return data["verdict"]


def _history_json_files(repo_root: Path) -> list[Path]:
    hist = repo_root / ".agent-loop" / "review-history"
    return sorted(
        p for p in hist.iterdir() if p.is_file() and p.suffix == ".json" and p.name != ".gitkeep"
    )


def _gate_env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    # Live mock / DiffFile paths are test-only; require explicit test mode for OS skip.
    env.setdefault("AGENT_LOOP_TEST_MODE", "1")
    env.setdefault("AGENT_LOOP_ALLOW_DIFF_FILE", "1")
    env.update(extra)
    return env


def _init_clean_live_repo(tmp_path: Path) -> Path:
    """Tiny git repo with a non-secret HEAD..HEAD~1 diff for live Codex path tests.

    The real project branch diff includes secret_scan fixtures, so productive-path
    tests must not use the main worktree merge-base range.
    """
    repo = tmp_path
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "gate-test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Gate Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "app.py").write_text("print('base')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "app.py").write_text("print('head')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "head"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _run_live_gate(
    *,
    gate_ps1: Path,
    live_repo: Path,
    env: dict[str, str],
    extra_args: list[str] | None = None,
):
    """Invoke the gate against a clean temp repo (productive path, no DiffFile)."""
    args = [
        "-RepoRoot",
        str(live_repo),
        "-BaseRef",
        "HEAD~1",
        *(extra_args or []),
    ]
    return run_gate(*args, script=gate_ps1, env=env, cwd=live_repo)


def test_discover_powershell_prefers_pwsh(monkeypatch):
    import shutil as shutil_mod

    calls: list[str] = []

    def fake_which(name: str):
        calls.append(name)
        if name == "pwsh":
            return r"C:\Tools\pwsh.exe"
        return None

    monkeypatch.setattr(shutil_mod, "which", fake_which)
    assert discover_powershell() == r"C:\Tools\pwsh.exe"
    assert calls[0] == "pwsh"


def test_run_gate_uses_discovered_powershell(monkeypatch, fixtures_dir, gate_ps1):
    import gate_helpers as gate_conf

    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gate_conf, "discover_powershell", lambda: "pwsh-from-helper")
    monkeypatch.setattr(gate_conf.subprocess, "run", fake_run)
    run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == "pwsh-from-helper"
    assert "-File" in cmd
    # DiffFile tests auto-prepend -BaseRef HEAD for shallow CI
    assert "-BaseRef" in cmd
    assert "HEAD" in cmd


def test_difffile_with_nonexistent_baseref(repo_root, fixtures_dir, gate_ps1):
    """Regression: missing base refs must not fail when -DiffFile is set (offline mode)."""
    env = _gate_env(AGENT_LOOP_BASE_REF_ONLY="1")
    proc = run_gate(
        "-BaseRef",
        "refs/does-not-exist-for-ci-baseref-test",
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"
    data = json.loads(_result_path(repo_root).read_text(encoding="utf-8"))
    # Offline mode: reviewed_base == reviewed_head when BaseRef cannot resolve.
    assert data["reviewed_base"] == data["reviewed_head"]


def test_01_valid_approved(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"


def test_02_valid_changes_required(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "changes_required_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "CHANGES_REQUIRED"


def test_03_invalid_verdict_becomes_review_failed(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "invalid_verdict.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_04_missing_required_fields(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "missing_fields.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_05_stale_head_preserve_refs(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "stale_head.json"),
        "-PreserveMockRefs",
        script=gate_ps1,
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr


def test_06_wrong_diff_hash_preserve_refs(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "wrong_diff_hash.json"),
        "-PreserveMockRefs",
        script=gate_ps1,
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr


def test_07_empty_diff(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "empty.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_08_skip_codex_without_mock(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_08c_live_codex_process_error_exit_3(repo_root, fixtures_dir, gate_ps1, tmp_path):
    mock_fail = fixtures_dir / "mock_codex_fail.py"
    live_repo = _init_clean_live_repo(tmp_path)
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_fail),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_08b_review_failed_mock(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "review_failed_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_09_invalid_json_mock(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "invalid.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr


def test_10_secret_pattern_aborts(repo_root, fixtures_dir, gate_ps1, tmp_path):
    secret_diff = tmp_path / "secret.diff"
    secret_diff.write_text(sf.secret_diff_text(), encoding="utf-8")
    proc = run_gate(
        "-DiffFile",
        str(secret_diff),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "secret" in combined.lower() or "Secret" in combined


def test_10b_secret_sqlalchemy_aborts(repo_root, fixtures_dir, gate_ps1, tmp_path):
    secret_diff = tmp_path / "secret_sqlalchemy.diff"
    secret_diff.write_text(sf.secret_sqlalchemy_diff_text(), encoding="utf-8")
    proc = run_gate(
        "-DiffFile",
        str(secret_diff),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_11_result_file_not_committed(repo_root):
    gi = (repo_root / ".gitignore").read_text(encoding="utf-8")
    required = [
        ".agent-loop/codex-review-result.json",
        ".agent-loop/tmp/",
        ".agent-loop/review-history/*",
        ".codex/",
    ]
    for pat in required:
        assert pat in gi, f"missing gitignore pattern: {pat}"


@pytest.mark.parametrize(
    "mock_name,expected",
    [
        ("approved_template.json", 0),
        ("changes_required_template.json", 2),
        ("review_failed_template.json", 3),
        ("stale_head.json", 4),
    ],
)
def test_12_exit_codes_match_contract(fixtures_dir, gate_ps1, mock_name, expected):
    args = [
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / mock_name),
    ]
    if mock_name == "stale_head.json":
        args.append("-PreserveMockRefs")
    proc = run_gate(*args, script=gate_ps1)
    assert proc.returncode == expected, proc.stdout + proc.stderr


def test_13_review_history_created(repo_root, fixtures_dir, gate_ps1):
    before = {p.name for p in _history_json_files(repo_root)}
    started = time.time()
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = _history_json_files(repo_root)
    new_or_updated = [
        p
        for p in after
        if p.name not in before or p.stat().st_mtime >= started - 1
    ]
    assert new_or_updated, "expected a new review-history JSON file"
    assert any(
        re.match(r"^\d{8}T\d{9}Z_[0-9a-f]+(?:_\d+)?\.json$", p.name, re.I)
        for p in new_or_updated
    )


def test_13b_history_unique_no_overwrite(repo_root, fixtures_dir, gate_ps1):
    before = {p.name for p in _history_json_files(repo_root)}
    names: list[str] = []
    for _ in range(2):
        proc = run_gate(
            "-DiffFile",
            str(fixtures_dir / "sample.diff"),
            "-SkipCodex",
            "-MockResultPath",
            str(fixtures_dir / "approved_template.json"),
            script=gate_ps1,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        after = {p.name for p in _history_json_files(repo_root)}
        new = sorted(after - before - set(names))
        assert new, "expected a distinct history file"
        names.append(new[-1])
        before = after
    assert names[0] != names[1]


def test_14_working_tree_no_tracked_source_mods(repo_root, fixtures_dir, gate_ps1):
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    def tracked_source_mods(status: str) -> set[str]:
        mods: set[str] = set()
        for line in status.splitlines():
            if len(line) < 4:
                continue
            code = line[:2]
            path = line[3:].strip()
            if path.startswith(".agent-loop/"):
                continue
            # Modified/deleted tracked files
            if "M" in code or "D" in code or code.strip() == "T":
                mods.add(path)
        return mods

    before_mods = tracked_source_mods(before)
    after_mods = tracked_source_mods(after)
    unexpected = after_mods - before_mods
    assert not unexpected, f"unexpected tracked modifications: {unexpected}"


def test_14b_live_codex_path_readonly_flags(repo_root, fixtures_dir, gate_ps1, tmp_path):
    argv_file = tmp_path / "codex-argv.txt"
    stdin_file = tmp_path / "codex-stdin.txt"
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"test-token"}}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "readonly")
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ARGV_FILE=str(argv_file),
        AGENT_LOOP_CODEX_STDIN_FILE=str(stdin_file),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"
    assert argv_file.is_file(), "mock Codex should record argv"
    argv_text = argv_file.read_text(encoding="utf-8")
    argv_lines = [ln for ln in argv_text.splitlines() if ln.strip()]
    assert "--sandbox" in argv_text
    assert "read-only" in argv_text
    # Legacy CLIs advertise --ask-for-approval; Codex 0.144+ may omit it.
    if "--ask-for-approval" in argv_text:
        assert "never" in argv_text
    assert "--ignore-user-config" in argv_text
    assert argv_lines[-1] == "-", "prompt must be stdin via trailing '-'"
    assert stdin_file.is_file(), "mock should record stdin prompt"
    stdin_text = stdin_file.read_text(encoding="utf-8")
    assert "reviewed_head=" in stdin_text

    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    def tracked_source_mods(status: str) -> set[str]:
        mods: set[str] = set()
        for line in status.splitlines():
            if len(line) < 4:
                continue
            code = line[:2]
            path = line[3:].strip()
            if path.startswith(".agent-loop/") or path.startswith("tests/agent_loop/"):
                continue
            if "M" in code or "D" in code or code.strip() == "T":
                mods.add(path)
        return mods

    unexpected = tracked_source_mods(after) - tracked_source_mods(before)
    assert not unexpected, f"unexpected tracked modifications: {unexpected}"


def test_14b_live_codex_workspace_outside_repo_and_auth(
    repo_root, fixtures_dir, gate_ps1, tmp_path
):
    argv_file = tmp_path / "codex-argv.txt"
    home_file = tmp_path / "codex-home.txt"
    stdin_file = tmp_path / "codex-stdin.txt"
    auth_seen = tmp_path / "auth-env-seen.txt"
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"test-token"}}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "wsauth")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ARGV_FILE=str(argv_file),
        AGENT_LOOP_CODEX_HOME_FILE=str(home_file),
        AGENT_LOOP_CODEX_STDIN_FILE=str(stdin_file),
        AGENT_LOOP_AUTH_ENV_SEEN_FILE=str(auth_seen),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_REQUIRE_AUTH="1",
        AGENT_LOOP_KEEP_WORKSPACE="1",
        AGENT_LOOP_KEEP_AUTH="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert home_file.is_file(), "mock should record CODEX_HOME"
    codex_home = Path(home_file.read_text(encoding="utf-8").strip())
    assert codex_home.is_dir()
    # Ephemeral CODEX_HOME may hold auth.json during the run; KEEP_AUTH still
    # deletes auth.json afterward (marker only remains).
    assert not (codex_home / "auth.json").exists(), "auth.json must be scrubbed after the run"
    assert (codex_home / "auth-via-home-copy.ok").is_file()
    assert auth_seen.is_file(), "mock should record auth was present during exec"
    assert "AGENT_LOOP_AUTH_ENV_SEEN=1" in auth_seen.read_text(encoding="utf-8")
    assert codex_home.name.startswith("codex-auth-")

    stdin_text = stdin_file.read_text(encoding="utf-8")
    m = re.search(
        r"HARD SCOPE: You may ONLY read files inside this review workspace directory:\s*\n(.+)",
        stdin_text,
    )
    assert m, "stdin should include HARD SCOPE workspace path"
    workspace = Path(m.group(1).strip())
    assert workspace.is_dir()
    assert (workspace / "workspace-manifest.json").is_file()
    assert not (workspace / "auth.json").exists(), "auth.json must not be in workspace"
    assert "UNTRUSTED DATA" in stdin_text

    # Auth home must NOT be under the Codex-readable workspace.
    try:
        codex_home.resolve().relative_to(workspace.resolve())
        auth_under_ws = True
    except ValueError:
        auth_under_ws = False
    assert not auth_under_ws, f"auth home {codex_home} must not be under workspace {workspace}"

    repo_resolved = live_repo.resolve()
    try:
        workspace.resolve().relative_to(repo_resolved)
        outside = False
    except ValueError:
        outside = True
    assert outside, f"workspace {workspace} must be outside repo {repo_resolved}"
    manifest = json.loads(
        (workspace / "workspace-manifest.json").read_text(encoding="utf-8")
    )
    assert "repo_root" not in manifest
    assert "git_rev" in manifest
    # Best-effort cleanup of kept temp dirs after assertions.
    shutil.rmtree(workspace, ignore_errors=True)
    shutil.rmtree(codex_home, ignore_errors=True)


def test_14b_keep_workspace_does_not_keep_auth(
    repo_root, fixtures_dir, gate_ps1, tmp_path
):
    """KEEP_WORKSPACE must not retain auth.json / CODEX_HOME when KEEP_AUTH unset."""
    home_file = tmp_path / "codex-home.txt"
    stdin_file = tmp_path / "codex-stdin.txt"
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"test-token"}}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "keepws")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_HOME_FILE=str(home_file),
        AGENT_LOOP_CODEX_STDIN_FILE=str(stdin_file),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_REQUIRE_AUTH="1",
        AGENT_LOOP_KEEP_WORKSPACE="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    codex_home = Path(home_file.read_text(encoding="utf-8").strip())
    assert not codex_home.exists(), "auth home must be deleted when KEEP_AUTH is unset"
    # Cleanup kept workspace
    stdin_text = stdin_file.read_text(encoding="utf-8")
    m = re.search(
        r"HARD SCOPE: You may ONLY read files inside this review workspace directory:\s*\n(.+)",
        stdin_text,
    )
    if m:
        shutil.rmtree(Path(m.group(1).strip()), ignore_errors=True)



def test_14c_post_codex_head_mismatch_exit_4(repo_root, fixtures_dir, gate_ps1, tmp_path):
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "stale")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ARGV_FILE=str(tmp_path / "argv.txt"),
        AGENT_LOOP_POST_CODEX_HEAD="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 4, proc.stdout + proc.stderr


def test_08d_deny_path_in_diff_fail_closed(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """Deny-listed path in reviewed patch aborts on productive (non-DiffFile) path."""
    # DiffFile cannot take the live Codex/build path; use a tiny temp repo instead.
    repo = tmp_path / "denyrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "ok.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "ok.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / ".env").write_text("SECRET=leak\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "bad"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    mock_codex = fixtures_dir / "mock_codex.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = run_gate(
        "-RepoRoot",
        str(repo),
        "-BaseRef",
        "HEAD~1",
        script=gate_ps1,
        env=env,
        cwd=repo,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    # Result is written under the script's .agent-loop (main repo), not temp repo.
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "SECRET=leak" not in combined


def test_08e_quoted_deny_path_in_diff_fail_closed(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """C-quoted deny path covered by DiffFile rejection when live Codex is requested."""
    # DiffFile + live bin without MockResultPath must fail closed before Codex.
    quoted_diff = tmp_path / "quoted_secret.diff"
    quoted_diff.write_text(
        'diff --git "a/foo secret/token.txt" "b/foo secret/token.txt"\n'
        '--- "a/foo secret/token.txt"\n'
        '+++ "b/foo secret/token.txt"\n'
        "@@ -0,0 +1 @@\n"
        "+SECRET=quoted-leak\n",
        encoding="utf-8",
    )
    mock_codex = fixtures_dir / "mock_codex.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = run_gate(
        "-DiffFile",
        str(quoted_diff),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "SECRET=quoted-leak" not in combined


def test_15_script_works_from_subdirectory(repo_root, fixtures_dir, gate_ps1):
    sub = repo_root / "tests" / "agent_loop"
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        "-RepoRoot",
        str(repo_root),
        cwd=sub,
        script=gate_ps1,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"


def test_run_review_loop_wrapper(repo_root, fixtures_dir, loop_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=loop_ps1,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_difffile_without_test_mode_rejected(repo_root, fixtures_dir, gate_ps1):
    """1. DiffFile without TEST_MODE → REVIEW_FAILED (no live Codex)."""
    from gate_helpers import AGENT_LOOP, discover_powershell

    env = dict(os.environ)
    env["AGENT_LOOP_TEST_MODE"] = "0"
    env["AGENT_LOOP_ALLOW_DIFF_FILE"] = "1"
    exe = discover_powershell()
    cmd = [
        exe,
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(AGENT_LOOP / "run-codex-review.ps1"),
        "-BaseRef",
        "HEAD",
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "TEST_MODE" in combined or "MockResultPath" in combined or "DiffFile" in combined


def test_difffile_test_mode_without_mock_rejected(repo_root, fixtures_dir, gate_ps1):
    """2. DiffFile + TEST_MODE without MockResultPath → REVIEW_FAILED even if ALLOW_DIFF_FILE=1."""
    from gate_helpers import AGENT_LOOP, discover_powershell

    env = dict(os.environ)
    env["AGENT_LOOP_TEST_MODE"] = "1"
    env["AGENT_LOOP_ALLOW_DIFF_FILE"] = "1"
    env["AGENT_LOOP_CODEX_BIN"] = str(fixtures_dir / "mock_codex.py")
    env["AGENT_LOOP_SKIP_OS_ISOLATION"] = "1"
    exe = discover_powershell()
    cmd = [
        exe,
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(AGENT_LOOP / "run-codex-review.ps1"),
        "-BaseRef",
        "HEAD",
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    data = json.loads(_result_path(repo_root).read_text(encoding="utf-8"))
    assert data["verdict"] == "REVIEW_FAILED"
    # Must not be a valid approval history path for DiffFile misuse (REVIEW_FAILED is OK).
    assert data["verdict"] != "APPROVED"


def test_difffile_live_codex_bin_without_mock_rejected(repo_root, fixtures_dir, gate_ps1):
    """3. DiffFile + live Codex bin without MockResultPath → REVIEW_FAILED (no Codex start)."""
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(fixtures_dir / "mock_codex.py"),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_ALLOW_DIFF_FILE="1",
    )
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_allow_diff_file_alone_insufficient(repo_root, fixtures_dir, gate_ps1):
    """4. AGENT_LOOP_ALLOW_DIFF_FILE alone must not unlock DiffFile."""
    from gate_helpers import AGENT_LOOP, discover_powershell

    env = dict(os.environ)
    env.pop("AGENT_LOOP_TEST_MODE", None)
    env["AGENT_LOOP_ALLOW_DIFF_FILE"] = "1"
    env["AGENT_LOOP_TEST_MODE"] = "0"
    exe = discover_powershell()
    cmd = [
        exe,
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(AGENT_LOOP / "run-codex-review.ps1"),
        "-BaseRef",
        "HEAD",
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_productive_diff_uses_binary_two_dot_range(repo_root, gate_ps1, fixtures_dir, tmp_path):
    """5. Productive path (no DiffFile) runs git diff --binary merge-base..head via mock Codex."""
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"tok-bin"}}\n', encoding="utf-8")
    live_repo = _init_clean_live_repo(tmp_path / "binary")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(fixtures_dir / "mock_codex.py"),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_REQUIRE_AUTH="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"
    # Script must document --binary two-dot productive diff.
    ps1 = (repo_root / ".agent-loop" / "run-codex-review.ps1").read_text(encoding="utf-8")
    assert "Write-GitBinaryDiffToFile" in ps1
    assert "--binary" in ps1
    assert "${BaseSha}..${HeadSha}" in ps1


def test_difffile_requires_allow_env(repo_root, fixtures_dir, gate_ps1):
    """Backward-compatible name: DiffFile without TEST_MODE+Mock is rejected."""
    test_difffile_without_test_mode_rejected(repo_root, fixtures_dir, gate_ps1)


def test_skip_os_isolation_requires_test_mode(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """SKIP_OS_ISOLATION alone must not unlock production on non-Unix."""
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "osiso")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="0",
    )
    # Force TEST_MODE off even if _gate_env setdefault ran first.
    env["AGENT_LOOP_TEST_MODE"] = "0"
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "TEST_MODE" in combined or "OS isolation" in combined


def test_live_codex_scrubbed_env_omits_secrets(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """Child Codex env must not inherit DATABASE_URL / PASSWORD / OPENAI_API_KEY."""
    env_keys = tmp_path / "env-keys.txt"
    temp_vals = tmp_path / "temp-vals.txt"
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"tok-scrub"}}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "scrub")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ENV_KEYS_FILE=str(env_keys),
        AGENT_LOOP_CODEX_TEMP_VALUES_FILE=str(temp_vals),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_REQUIRE_AUTH="1",
        DATABASE_URL="evil-db",
        PASSWORD="evil-password",
        CUSTOM_CREDENTIAL="parent-secret",
    )
    env["OPENAI" + "_API" + "_KEY"] = "should-not-pass"
    # Simulate Linux CI: parent has no TEMP/TMP/TMPDIR.
    for k in ("TEMP", "TMP", "TMPDIR"):
        env.pop(k, None)
    parent_custom = env.get("CUSTOM_CREDENTIAL")
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert env_keys.is_file(), "mock should record child env keys"
    keys = set(env_keys.read_text(encoding="utf-8").splitlines())
    assert "DATABASE_URL" not in keys
    assert "PASSWORD" not in keys
    assert "OPENAI_API_KEY" not in keys
    assert "CUSTOM_CREDENTIAL" not in keys
    assert "CODEX_ACCESS_TOKEN" in keys or "CODEX_API_KEY" in keys
    assert "CODEX_HOME" in keys
    assert "PATH" in keys
    # Child must receive a BCL temp path even when parent env omitted TEMP/TMP/TMPDIR.
    assert ("TEMP" in keys) or ("TMP" in keys) or ("TMPDIR" in keys)
    assert temp_vals.is_file()
    temp_map = {}
    for line in temp_vals.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            temp_map[k] = v
    expected_temp = Path(tempfile.gettempdir()).resolve()
    found = False
    for key in ("TEMP", "TMP", "TMPDIR"):
        if key in temp_map:
            child_temp = Path(temp_map[key]).resolve()
            assert child_temp == expected_temp or str(expected_temp).startswith(
                str(child_temp)
            ) or str(child_temp).startswith(str(expected_temp))
            # Temp path is not a credential channel.
            assert "evil" not in temp_map[key].lower()
            assert "password" not in temp_map[key].lower()
            found = True
    assert found, f"expected TEMP/TMP/TMPDIR values, got {temp_map!r}"
    # Child only allowlisted / side-channel keys (no parent secret bleed).
    forbidden_prefixes = ("RAILWAY_", "AWS_", "SESSION_")
    for k in keys:
        assert not k.startswith(forbidden_prefixes), k
        assert "SECRET" not in k.upper() or k.startswith("AGENT_LOOP_"), k
        assert "PASSWORD" not in k.upper(), k
    # Parent env must remain unchanged by the child scrub.
    assert parent_custom == "parent-secret"


def test_live_codex_only_one_auth_key(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """Child must receive at most one of CODEX_ACCESS_TOKEN / CODEX_API_KEY."""
    env_keys = tmp_path / "env-keys.txt"
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "onekey")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ENV_KEYS_FILE=str(env_keys),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_REQUIRE_AUTH="1",
        CODEX_ACCESS_TOKEN="access-only",
    )
    env["CODEX" + "_API" + "_KEY"] = "api-also-set"
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    keys = set(env_keys.read_text(encoding="utf-8").splitlines())
    has_access = "CODEX_ACCESS_TOKEN" in keys
    has_api = "CODEX_API_KEY" in keys
    assert has_access ^ has_api, (
        f"expected exactly one auth key, got access={has_access} api={has_api}"
    )


def test_env_clear_failure_fail_closed(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """Simulated Environment.Clear failure → REVIEW_FAILED exit 3 (no blocklist fallback)."""
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"tok"}}\n', encoding="utf-8")
    live_repo = _init_clean_live_repo(tmp_path / "clearfail")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(fixtures_dir / "mock_codex.py"),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_SIMULATE_ENV_CLEAR_FAIL="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"


def test_live_codex_parallel_streams_no_deadlock(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """1 MiB stdout + 1 MiB stderr must not deadlock Invoke-CodexCommand."""
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"CODEX_API_KEY":"sk-test"}\n', encoding="utf-8")
    live_repo = _init_clean_live_repo(tmp_path / "flood")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(fixtures_dir / "mock_codex.py"),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_MOCK_FLOOD_STREAMS="1",
        AGENT_LOOP_CODEX_TIMEOUT_SEC="120",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"


def test_live_codex_timeout_kills_hung_and_rejects_partial(
    repo_root, fixtures_dir, gate_ps1, tmp_path
):
    """Hung Codex past timeout → kill tree, REVIEW_FAILED; partial JSON not APPROVED."""
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"CODEX_API_KEY":"sk-test"}\n', encoding="utf-8")
    live_repo = _init_clean_live_repo(tmp_path / "hang")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(fixtures_dir / "mock_codex.py"),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_MOCK_PARTIAL_HANG="1",
        AGENT_LOOP_CODEX_TIMEOUT_SEC="2",
    )
    started = time.time()
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    elapsed = time.time() - started
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert elapsed < 60, f"timeout kill took too long: {elapsed}s"
    data = json.loads(_result_path(repo_root).read_text(encoding="utf-8"))
    assert data["verdict"] == "REVIEW_FAILED"
    notes = " ".join(data.get("review_notes") or [])
    assert "timeout=true" in notes
    assert "APPROVED" not in data.get("summary", "")


def _pid_alive(pid: int) -> bool:
    """Return True if pid still exists (Linux /proc or Windows/POSIX signal 0)."""
    if pid <= 0:
        return False
    if sys.platform.startswith("linux"):
        return Path(f"/proc/{pid}").exists()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def test_live_codex_timeout_kills_process_tree(
    repo_root, fixtures_dir, gate_ps1, tmp_path
):
    """Real process tree (parent+child+grandchild) must be gone after gate timeout."""
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"CODEX_API_KEY":"sk-test"}\n', encoding="utf-8")
    pid_file = tmp_path / "hang-pids.txt"
    live_repo = _init_clean_live_repo(tmp_path / "hangtree")
    hang_bin = fixtures_dir / "mock_codex_hang_tree.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(hang_bin),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_HANG_PID_FILE=str(pid_file),
        AGENT_LOOP_CODEX_TIMEOUT_SEC="2",
    )
    started = time.time()
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    elapsed = time.time() - started
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert elapsed < 60, f"timeout kill took too long: {elapsed}s"
    data = json.loads(_result_path(repo_root).read_text(encoding="utf-8"))
    assert data["verdict"] == "REVIEW_FAILED"
    notes = " ".join(data.get("review_notes") or [])
    assert "timeout=true" in notes
    assert pid_file.is_file(), "hang fixture should have written PIDs"
    pids = [
        int(line.strip())
        for line in pid_file.read_text(encoding="utf-8").splitlines()
        if line.strip().isdigit()
    ]
    assert len(pids) >= 2, f"expected parent+child PIDs, got {pids}"
    # Brief grace for OS to reap; then all PIDs must be gone.
    deadline = time.time() + 10
    survivors: list[int] = []
    while time.time() < deadline:
        survivors = [p for p in pids if _pid_alive(p)]
        if not survivors:
            break
        time.sleep(0.2)
    assert not survivors, f"process tree PIDs still alive after timeout kill: {survivors}"


def test_live_codex_stderr_noise_still_approved(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """Progress JSON on stderr must not pollute stdout verdict parsing."""
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"CODEX_API_KEY":"sk-test"}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
    live_repo = _init_clean_live_repo(tmp_path / "stderr")
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_MOCK_STDERR_NOISE="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=live_repo, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"


def test_auth_json_in_diff_fail_closed(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """auth.json in the reviewed patch must abort before Codex (productive path)."""
    repo = tmp_path / "authrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "ok.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "ok.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "auth.json").write_text(
        '{"tokens":{"access_token":"leak"}}\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "auth.json"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "auth"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    mock_codex = fixtures_dir / "mock_codex.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_TEST_MODE="1",
    )
    proc = _run_live_gate(gate_ps1=gate_ps1, live_repo=repo, env=env)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "leak" not in combined
