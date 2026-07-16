#!/usr/bin/env python3
"""Scan diff or text for secret-like patterns before sending input to Codex.

Exit codes:
  0 - no secret patterns found
  1 - one or more secret patterns found
  2 - usage / I/O error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key_assignment", re.compile(r"(?i)api[_-]?key\s*=")),
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_access_key", re.compile(r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*=")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    ("postgres_url_with_password", re.compile(r"(?i)postgres(?:ql)?://[^:\s/]+:[^@\s/]+@")),
    (
        "sqlalchemy_postgres_url_with_password",
        re.compile(r"(?i)postgres(?:ql)?\+[A-Za-z0-9_]+://[^:\s/]+:[^@\s/]+@"),
    ),
    ("mysql_url_with_password", re.compile(r"(?i)mysql://[^:\s/]+:[^@\s/]+@")),
    ("generic_db_url_password", re.compile(r"(?i)(?:mongodb|redis|amqp)://[^:\s/]+:[^@\s/]+@")),
    (
        "database_url_with_password",
        re.compile(
            r"(?i)database_url\s*[=:]\s*\S*://[^:\s/]+:[^@\s/]+@"
        ),
    ),
    ("railway_token_assignment", re.compile(r"(?i)railway_token\s*[=:]\s*\S+")),
    ("session_secret_assignment", re.compile(r"(?i)session_secret\s*[=:]\s*\S+")),
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
]


@dataclass(frozen=True)
class SecretMatch:
    pattern_name: str
    line_number: int


def scan_text(text: str) -> list[SecretMatch]:
    """Return all secret-pattern matches in *text* (line-oriented).

    When *text* looks like a unified diff, only added lines (``+``, excluding
    ``+++`` headers) are scanned. Deletion hunks and context are ignored so
    removing legacy fixtures does not abort a review, while newly introduced
    secrets still fail closed.
    """
    matches: list[SecretMatch] = []
    looks_like_diff = text.startswith("diff --git ") or "\ndiff --git " in text
    for line_number, line in enumerate(text.splitlines(), start=1):
        if looks_like_diff:
            if not line.startswith("+") or line.startswith("+++"):
                continue
            content = line[1:]
        else:
            content = line
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(content):
                matches.append(
                    SecretMatch(
                        pattern_name=name,
                        line_number=line_number,
                    )
                )
                break
    return matches


def scan_file(path: Path) -> list[SecretMatch]:
    """Scan a file as UTF-8 text (BOM stripped if present)."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    return scan_text(text)


def format_matches(matches: list[SecretMatch]) -> str:
    """Format matches for CLI stderr: pattern name + line number only (no secrets)."""
    lines = [f"  line {m.line_number}: [{m.pattern_name}]" for m in matches]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a diff or text file for secret-like patterns."
    )
    parser.add_argument(
        "--diff",
        required=True,
        type=Path,
        help="Path to diff or text file to scan",
    )
    args = parser.parse_args(argv)

    if not args.diff.is_file():
        print(f"secret_scan: file not found: {args.diff}", file=sys.stderr)
        return 2

    try:
        matches = scan_file(args.diff)
    except OSError as exc:
        print(f"secret_scan: read error: {exc}", file=sys.stderr)
        return 2

    if matches:
        print(
            f"secret_scan: ABORT - {len(matches)} secret-like pattern(s) found; "
            "refusing to send diff to Codex.",
            file=sys.stderr,
        )
        print(format_matches(matches), file=sys.stderr)
        return 1

    print("secret_scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
