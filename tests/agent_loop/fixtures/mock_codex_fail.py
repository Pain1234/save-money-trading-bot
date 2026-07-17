#!/usr/bin/env python3
"""Fake Codex CLI that fails on real exec (process-error gate tests)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Keep in sync with mock_codex.py HELP_TEXT so flag detection still works.
HELP_TEXT = """
Usage: codex exec [OPTIONS] <INSTRUCTION>

Options:
  --skip-git-repo-check
  --sandbox <MODE>           e.g. read-only
  --ignore-user-config
  --ignore-rules
  --ephemeral
"""


def main(argv: list[str]) -> int:
    argv_file = os.environ.get("AGENT_LOOP_CODEX_ARGV_FILE", "").strip()
    if argv_file:
        Path(argv_file).write_text("\n".join(argv) + "\n", encoding="utf-8")

    if len(argv) >= 2 and argv[0] == "exec" and "--help" in argv:
        print(HELP_TEXT)
        return 0

    if not argv or argv[0] != "exec":
        print("mock_codex_fail: expected 'exec' subcommand", file=sys.stderr)
        return 2

    # Drain stdin when prompt is piped (last arg "-") so the pipe does not break.
    if argv[-1] == "-":
        _ = sys.stdin.read()

    print("mock_codex_fail: simulated Codex process failure", file=sys.stderr)
    return 7


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
