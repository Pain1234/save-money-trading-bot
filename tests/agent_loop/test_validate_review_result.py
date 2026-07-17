"""Pure Python tests for validate-review-result.py."""

from __future__ import annotations

import json
from pathlib import Path


def _load_fixture(fixtures_dir: Path, name: str) -> dict | str:
    path = fixtures_dir / name
    text = path.read_text(encoding="utf-8")
    if name.endswith(".json") and name != "invalid.json":
        return json.loads(text)
    return text


def _fill_refs(data: dict, *, head: str, base: str, diff_hash: str) -> dict:
    out = dict(data)
    out["reviewed_head"] = head
    out["reviewed_base"] = base
    out["reviewed_diff_hash"] = diff_hash
    return out


HEAD = "a" * 40
BASE = "b" * 40
DIFF = "c" * 64


def test_valid_approved(validate_mod, schema_path, fixtures_dir, tmp_path):
    schema = validate_mod.load_schema(schema_path)
    data = _fill_refs(
        _load_fixture(fixtures_dir, "approved_template.json"),
        head=HEAD,
        base=BASE,
        diff_hash=DIFF,
    )
    validate_mod.validate_review_result(
        data, schema, expected_head=HEAD, expected_base=BASE, expected_diff_hash=DIFF
    )
    result = tmp_path / "ok.json"
    result.write_text(json.dumps(data), encoding="utf-8")
    assert (
        validate_mod.main(
            [
                "--result",
                str(result),
                "--schema",
                str(schema_path),
                "--expected-head",
                HEAD,
                "--expected-base",
                BASE,
                "--expected-diff-hash",
                DIFF,
            ]
        )
        == 0
    )


def test_valid_changes_required(validate_mod, schema_path, fixtures_dir):
    schema = validate_mod.load_schema(schema_path)
    data = _fill_refs(
        _load_fixture(fixtures_dir, "changes_required_template.json"),
        head=HEAD,
        base=BASE,
        diff_hash=DIFF,
    )
    validate_mod.validate_review_result(
        data, schema, expected_head=HEAD, expected_base=BASE, expected_diff_hash=DIFF
    )


def test_invalid_verdict(validate_mod, schema_path, fixtures_dir, tmp_path):
    data = _fill_refs(
        _load_fixture(fixtures_dir, "invalid_verdict.json"),
        head=HEAD,
        base=BASE,
        diff_hash=DIFF,
    )
    result = tmp_path / "bad_verdict.json"
    result.write_text(json.dumps(data), encoding="utf-8")
    code = validate_mod.main(
        ["--result", str(result), "--schema", str(schema_path)]
    )
    assert code == validate_mod.EXIT_INVALID


def test_missing_required_fields(validate_mod, schema_path, fixtures_dir, tmp_path):
    data = _fill_refs(
        _load_fixture(fixtures_dir, "missing_fields.json"),
        head=HEAD,
        base=BASE,
        diff_hash=DIFF,
    )
    result = tmp_path / "missing.json"
    result.write_text(json.dumps(data), encoding="utf-8")
    code = validate_mod.main(
        ["--result", str(result), "--schema", str(schema_path)]
    )
    assert code == validate_mod.EXIT_INVALID


def test_stale_head_sha(validate_mod, schema_path, fixtures_dir, tmp_path):
    data = _load_fixture(fixtures_dir, "stale_head.json")
    data = dict(data)
    data["reviewed_base"] = BASE
    data["reviewed_diff_hash"] = DIFF
    # keep deadbeef head
    result = tmp_path / "stale.json"
    result.write_text(json.dumps(data), encoding="utf-8")
    code = validate_mod.main(
        [
            "--result",
            str(result),
            "--schema",
            str(schema_path),
            "--expected-head",
            HEAD,
            "--expected-base",
            BASE,
            "--expected-diff-hash",
            DIFF,
        ]
    )
    assert code == validate_mod.EXIT_STALE


def test_wrong_diff_hash(validate_mod, schema_path, fixtures_dir, tmp_path):
    data = _load_fixture(fixtures_dir, "wrong_diff_hash.json")
    data = dict(data)
    data["reviewed_head"] = HEAD
    data["reviewed_base"] = BASE
    # keep wrong hash
    result = tmp_path / "wrong_hash.json"
    result.write_text(json.dumps(data), encoding="utf-8")
    code = validate_mod.main(
        [
            "--result",
            str(result),
            "--schema",
            str(schema_path),
            "--expected-head",
            HEAD,
            "--expected-base",
            BASE,
            "--expected-diff-hash",
            DIFF,
        ]
    )
    assert code == validate_mod.EXIT_STALE


def test_invalid_json(validate_mod, schema_path, fixtures_dir):
    path = fixtures_dir / "invalid.json"
    code = validate_mod.main(
        ["--result", str(path), "--schema", str(schema_path)]
    )
    assert code == validate_mod.EXIT_USAGE


def test_check_verdict_rules_approved_with_major_fails(validate_mod):
    data = {
        "verdict": "APPROVED",
        "findings": [
            {
                "id": "X",
                "severity": "MAJOR",
                "category": "CORRECTNESS",
                "file": "a.py",
                "line_start": 1,
                "line_end": 1,
                "problem": "p",
                "evidence": "e",
                "required_fix": "f",
            }
        ],
    }
    errs = validate_mod.check_verdict_rules(data)
    assert errs


def test_check_verdict_rules_changes_required_only_minor_fails(validate_mod):
    data = {
        "verdict": "CHANGES_REQUIRED",
        "findings": [
            {
                "id": "Y",
                "severity": "MINOR",
                "category": "DOCUMENTATION",
                "file": "a.py",
                "line_start": 1,
                "line_end": 1,
                "problem": "p",
                "evidence": "e",
                "required_fix": "f",
            }
        ],
    }
    errs = validate_mod.check_verdict_rules(data)
    assert errs


def test_check_verdict_rules_review_failed_empty_ok(validate_mod):
    data = {"verdict": "REVIEW_FAILED", "findings": []}
    assert validate_mod.check_verdict_rules(data) == []
