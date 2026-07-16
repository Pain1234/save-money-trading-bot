"""Integration tests for run-codex-review.ps1 gate (15 categories)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from conftest import run_gate


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
        re.match(r".+_\d+.*\.json$", p.name) or re.match(r".+_.*\.json$", p.name)
        for p in new_or_updated
    )


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
