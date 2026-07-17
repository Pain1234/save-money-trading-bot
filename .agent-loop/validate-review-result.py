#!/usr/bin/env python3
"""Validate Codex review result JSON against schema 1.0 and verdict rules.

Exit codes:
  0 - validation succeeded
  1 - schema / verdict-rule failure
  2 - usage / I/O / invalid JSON / missing dependency
  4 - expected base / head / diff-hash mismatch (stale or wrong review)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover - exercised only when dep missing
    jsonschema = None  # type: ignore[assignment]
    Draft7Validator = None  # type: ignore[misc, assignment]

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_STALE = 4

SEVERITY_BLOCKING = frozenset({"BLOCKER", "MAJOR"})


class ValidationError(Exception):
    """Structured validation failure with exit code."""

    def __init__(self, message: str, *, exit_code: int = EXIT_INVALID) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}", exit_code=EXIT_USAGE) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"invalid JSON in {path}: {exc}", exit_code=EXIT_USAGE
        ) from exc


def load_schema(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValidationError(f"schema root must be object: {path}", exit_code=EXIT_USAGE)
    return data


def validate_against_schema(data: Any, schema: dict[str, Any]) -> list[str]:
    """Return a list of schema error messages (empty if valid)."""
    if Draft7Validator is None:
        raise ValidationError(
            "jsonschema package is required (pip install jsonschema)",
            exit_code=EXIT_USAGE,
        )
    validator = Draft7Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.path) or "<root>"
        errors.append(f"{path}: {error.message}")
    return errors


def blocking_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    findings = data.get("findings") or []
    if not isinstance(findings, list):
        return []
    out: list[dict[str, Any]] = []
    for finding in findings:
        if isinstance(finding, dict) and finding.get("severity") in SEVERITY_BLOCKING:
            out.append(finding)
    return out


def check_verdict_rules(data: dict[str, Any]) -> list[str]:
    """Enforce APPROVED / CHANGES_REQUIRED / REVIEW_FAILED finding rules.

    REVIEW_FAILED may have empty or any findings.
    APPROVED must not contain BLOCKER or MAJOR.
    CHANGES_REQUIRED must contain at least one BLOCKER or MAJOR.
    """
    errors: list[str] = []
    verdict = data.get("verdict")
    blocking = blocking_findings(data)

    if verdict == "APPROVED" and blocking:
        ids = ", ".join(str(f.get("id", "?")) for f in blocking)
        errors.append(
            f"APPROVED must not contain BLOCKER/MAJOR findings (found: {ids})"
        )
    elif verdict == "CHANGES_REQUIRED" and not blocking:
        errors.append(
            "CHANGES_REQUIRED requires at least one BLOCKER or MAJOR finding"
        )
    # REVIEW_FAILED: no finding-count constraints
    return errors


def check_expected_refs(
    data: dict[str, Any],
    *,
    expected_head: str | None = None,
    expected_base: str | None = None,
    expected_diff_hash: str | None = None,
) -> list[str]:
    """Return mismatch messages for provided expected-* values."""
    errors: list[str] = []
    if expected_head is not None and data.get("reviewed_head") != expected_head:
        errors.append(
            f"reviewed_head mismatch: got {data.get('reviewed_head')!r}, "
            f"expected {expected_head!r}"
        )
    if expected_base is not None and data.get("reviewed_base") != expected_base:
        errors.append(
            f"reviewed_base mismatch: got {data.get('reviewed_base')!r}, "
            f"expected {expected_base!r}"
        )
    if expected_diff_hash is not None and data.get("reviewed_diff_hash") != expected_diff_hash:
        errors.append(
            f"reviewed_diff_hash mismatch: got {data.get('reviewed_diff_hash')!r}, "
            f"expected {expected_diff_hash!r}"
        )
    return errors


def validate_review_result(
    data: Any,
    schema: dict[str, Any],
    *,
    expected_head: str | None = None,
    expected_base: str | None = None,
    expected_diff_hash: str | None = None,
) -> None:
    """Validate *data*; raise ValidationError on failure."""
    if not isinstance(data, dict):
        raise ValidationError("review result root must be a JSON object")

    schema_errors = validate_against_schema(data, schema)
    if schema_errors:
        raise ValidationError("schema validation failed:\n  " + "\n  ".join(schema_errors))

    verdict_errors = check_verdict_rules(data)
    if verdict_errors:
        raise ValidationError("verdict rules failed:\n  " + "\n  ".join(verdict_errors))

    stale_errors = check_expected_refs(
        data,
        expected_head=expected_head,
        expected_base=expected_base,
        expected_diff_hash=expected_diff_hash,
    )
    if stale_errors:
        raise ValidationError(
            "stale/wrong review refs:\n  " + "\n  ".join(stale_errors),
            exit_code=EXIT_STALE,
        )


def validate_review_result_file(
    result_path: Path,
    schema_path: Path,
    *,
    expected_head: str | None = None,
    expected_base: str | None = None,
    expected_diff_hash: str | None = None,
) -> dict[str, Any]:
    """Load and validate a result file; return the parsed object on success."""
    schema = load_schema(schema_path)
    data = load_json(result_path)
    validate_review_result(
        data,
        schema,
        expected_head=expected_head,
        expected_base=expected_base,
        expected_diff_hash=expected_diff_hash,
    )
    assert isinstance(data, dict)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Codex review result JSON (schema 1.0 + verdict rules)."
    )
    parser.add_argument("--result", required=True, type=Path, help="Path to result JSON")
    parser.add_argument("--schema", required=True, type=Path, help="Path to JSON Schema")
    parser.add_argument("--expected-head", default=None, help="Expected reviewed_head SHA")
    parser.add_argument("--expected-base", default=None, help="Expected reviewed_base ref/SHA")
    parser.add_argument(
        "--expected-diff-hash",
        default=None,
        help="Expected reviewed_diff_hash (SHA256 hex)",
    )
    args = parser.parse_args(argv)

    try:
        validate_review_result_file(
            args.result,
            args.schema,
            expected_head=args.expected_head,
            expected_base=args.expected_base,
            expected_diff_hash=args.expected_diff_hash,
        )
    except ValidationError as exc:
        print(f"validate-review-result: FAIL - {exc}", file=sys.stderr)
        return exc.exit_code

    print("validate-review-result: OK")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
