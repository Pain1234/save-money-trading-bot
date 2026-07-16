#!/usr/bin/env python3
"""Fake Codex CLI for gate tests: records argv and emits APPROVED JSON."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HELP_TEXT = """
Usage: codex exec [OPTIONS] <INSTRUCTION>

Options:
  --skip-git-repo-check
  --sandbox <MODE>           e.g. read-only
  --ask-for-approval <WHEN>  e.g. never
  --ignore-user-config
  --ignore-rules
  --ephemeral
"""


def _parse_refs(instruction_path: Path) -> dict[str, str]:
    text = instruction_path.read_text(encoding="utf-8")
    refs: dict[str, str] = {}
    for key in ("reviewed_base", "reviewed_head", "reviewed_diff_hash"):
        m = re.search(rf"^{key}=(\S+)\s*$", text, re.MULTILINE)
        if not m:
            raise SystemExit(f"mock_codex: missing {key} in instruction")
        refs[key] = m.group(1)
    return refs


def main(argv: list[str]) -> int:
    argv_file = os.environ.get("AGENT_LOOP_CODEX_ARGV_FILE", "").strip()
    if argv_file:
        Path(argv_file).write_text("\n".join(argv) + "\n", encoding="utf-8")

    home_file = os.environ.get("AGENT_LOOP_CODEX_HOME_FILE", "").strip()
    if home_file:
        Path(home_file).write_text(os.environ.get("CODEX_HOME", "") + "\n", encoding="utf-8")

    if len(argv) >= 2 and argv[0] == "exec" and "--help" in argv:
        print(HELP_TEXT)
        return 0

    if not argv or argv[0] != "exec":
        print("mock_codex: expected 'exec' subcommand", file=sys.stderr)
        return 2

    if os.environ.get("AGENT_LOOP_REQUIRE_AUTH", "").strip() == "1":
        codex_home = os.environ.get("CODEX_HOME", "").strip()
        auth = Path(codex_home) / "auth.json" if codex_home else None
        if auth is None or not auth.is_file():
            print("mock_codex: auth.json missing under CODEX_HOME", file=sys.stderr)
            return 3

    instruction = Path(argv[-1])
    if not instruction.is_file():
        print(f"mock_codex: instruction not found: {instruction}", file=sys.stderr)
        return 2

    refs = _parse_refs(instruction)
    payload = {
        "schema_version": "1.0",
        "verdict": "APPROVED",
        "reviewed_base": refs["reviewed_base"],
        "reviewed_head": refs["reviewed_head"],
        "reviewed_diff_hash": refs["reviewed_diff_hash"],
        "summary": "Mock Codex approved (test).",
        "findings": [],
        "required_tests": [],
        "review_notes": ["mock_codex"],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
