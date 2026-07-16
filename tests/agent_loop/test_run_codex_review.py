"""Integration tests for run-codex-review.ps1 gate."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
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
    env.update(extra)
    return env


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


def test_08c_live_codex_process_error_exit_3(repo_root, fixtures_dir, gate_ps1):
    mock_fail = fixtures_dir / "mock_codex_fail.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_fail),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        script=gate_ps1,
        env=env,
    )
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


def test_10_secret_pattern_aborts(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "secret.diff"),
        "-SkipCodex",
        "-MockResultPath",
        str(fixtures_dir / "approved_template.json"),
        script=gate_ps1,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "secret" in combined.lower() or "Secret" in combined


def test_10b_secret_sqlalchemy_aborts(repo_root, fixtures_dir, gate_ps1):
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "secret_sqlalchemy.diff"),
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
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"test-token"}}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
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
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
    )
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "APPROVED"
    assert argv_file.is_file(), "mock Codex should record argv"
    argv_text = argv_file.read_text(encoding="utf-8")
    assert "--sandbox" in argv_text
    assert "read-only" in argv_text
    assert "--ask-for-approval" in argv_text
    assert "never" in argv_text
    assert "--ignore-user-config" in argv_text

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
    auth_src = tmp_path / "auth.json"
    auth_src.write_text('{"tokens":{"access_token":"test-token"}}\n', encoding="utf-8")
    mock_codex = fixtures_dir / "mock_codex.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ARGV_FILE=str(argv_file),
        AGENT_LOOP_CODEX_HOME_FILE=str(home_file),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
        AGENT_LOOP_AUTH_JSON_SOURCE=str(auth_src),
        AGENT_LOOP_REQUIRE_AUTH="1",
        AGENT_LOOP_KEEP_WORKSPACE="1",
    )
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert home_file.is_file(), "mock should record CODEX_HOME"
    codex_home = Path(home_file.read_text(encoding="utf-8").strip())
    assert codex_home.is_dir()
    assert (codex_home / "auth.json").is_file()
    workspace = codex_home.parent
    repo_resolved = repo_root.resolve()
    try:
        workspace.resolve().relative_to(repo_resolved)
        outside = False
    except ValueError:
        outside = True
    assert outside, f"workspace {workspace} must be outside repo {repo_resolved}"
    assert (workspace / "workspace-manifest.json").is_file()
    manifest = json.loads(
        (workspace / "workspace-manifest.json").read_text(encoding="utf-8")
    )
    assert "repo_root" not in manifest
    assert "git_rev" in manifest
    # Best-effort cleanup of kept temp workspace after assertions.
    shutil.rmtree(workspace, ignore_errors=True)


def test_14c_post_codex_head_mismatch_exit_4(repo_root, fixtures_dir, gate_ps1, tmp_path):
    mock_codex = fixtures_dir / "mock_codex.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_CODEX_ARGV_FILE=str(tmp_path / "argv.txt"),
        AGENT_LOOP_POST_CODEX_HEAD="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = run_gate(
        "-DiffFile",
        str(fixtures_dir / "sample.diff"),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr


def test_08d_deny_path_in_diff_fail_closed(repo_root, fixtures_dir, gate_ps1, tmp_path):
    """Deny-listed path in the reviewed patch must abort before Codex."""
    env_diff = tmp_path / "env_in_patch.diff"
    env_diff.write_text(
        "diff --git a/.env b/.env\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -0,0 +1 @@\n"
        "+SECRET=leak\n",
        encoding="utf-8",
    )
    mock_codex = fixtures_dir / "mock_codex.py"
    env = _gate_env(
        AGENT_LOOP_CODEX_BIN=str(mock_codex),
        AGENT_LOOP_SKIP_OS_ISOLATION="1",
    )
    proc = run_gate(
        "-DiffFile",
        str(env_diff),
        script=gate_ps1,
        env=env,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert _read_verdict(repo_root) == "REVIEW_FAILED"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "SECRET=leak" not in combined


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
