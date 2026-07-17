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
  --output-last-message <FILE>
"""


def _parse_refs(text: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for key in ("reviewed_base", "reviewed_head", "reviewed_diff_hash"):
        m = re.search(rf"^{key}=(\S+)\s*$", text, re.MULTILINE)
        if not m:
            raise SystemExit(f"mock_codex: missing {key} in instruction")
        refs[key] = m.group(1)
    return refs


def _output_last_message_path(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg == "--output-last-message" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv: list[str]) -> int:
    argv_file = os.environ.get("AGENT_LOOP_CODEX_ARGV_FILE", "").strip()
    if argv_file:
        Path(argv_file).write_text("\n".join(argv) + "\n", encoding="utf-8")

    home_file = os.environ.get("AGENT_LOOP_CODEX_HOME_FILE", "").strip()
    if home_file:
        Path(home_file).write_text(os.environ.get("CODEX_HOME", "") + "\n", encoding="utf-8")

    env_keys_file = os.environ.get("AGENT_LOOP_CODEX_ENV_KEYS_FILE", "").strip()
    if env_keys_file:
        Path(env_keys_file).write_text(
            "\n".join(sorted(os.environ.keys())) + "\n",
            encoding="utf-8",
        )

    temp_values_file = os.environ.get("AGENT_LOOP_CODEX_TEMP_VALUES_FILE", "").strip()
    if temp_values_file:
        lines: list[str] = []
        for key in ("TEMP", "TMP", "TMPDIR"):
            val = os.environ.get(key, "")
            if val:
                lines.append(f"{key}={val}")
        Path(temp_values_file).write_text(
            "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )

    if len(argv) >= 2 and argv[0] == "exec" and "--help" in argv:
        print(HELP_TEXT)
        return 0

    if not argv or argv[0] != "exec":
        print("mock_codex: expected 'exec' subcommand", file=sys.stderr)
        return 2

    if os.environ.get("AGENT_LOOP_REQUIRE_AUTH", "").strip() == "1":
        mock_ok = os.environ.get("AGENT_LOOP_MOCK_AUTH_OK", "").strip() == "1"
        has_key = bool(
            os.environ.get("CODEX_ACCESS_TOKEN", "").strip()
            or os.environ.get("CODEX_API_KEY", "").strip()
        )
        if not mock_ok and not has_key:
            print(
                "mock_codex: CODEX_ACCESS_TOKEN/CODEX_API_KEY missing "
                "(or set AGENT_LOOP_MOCK_AUTH_OK=1)",
                file=sys.stderr,
            )
            return 3
        seen_file = os.environ.get("AGENT_LOOP_AUTH_ENV_SEEN_FILE", "").strip()
        if seen_file and has_key:
            Path(seen_file).write_text("AGENT_LOOP_AUTH_ENV_SEEN=1\n", encoding="utf-8")

    if argv[-1] == "-":
        instruction_text = sys.stdin.read()
    else:
        instruction = Path(argv[-1])
        if not instruction.is_file():
            print(f"mock_codex: instruction not found: {instruction}", file=sys.stderr)
            return 2
        instruction_text = instruction.read_text(encoding="utf-8")

    stdin_file = os.environ.get("AGENT_LOOP_CODEX_STDIN_FILE", "").strip()
    if stdin_file:
        Path(stdin_file).write_text(instruction_text, encoding="utf-8")

    if os.environ.get("AGENT_LOOP_MOCK_STDERR_NOISE", "").strip() == "1":
        print("{progress}", file=sys.stderr)

    if os.environ.get("AGENT_LOOP_MOCK_FLOOD_STREAMS", "").strip() == "1":
        # 1 MiB on each stream to exercise parallel ReadToEndAsync (no deadlock).
        chunk = "x" * (1024 * 1024)
        sys.stdout.write(chunk)
        sys.stdout.flush()
        sys.stderr.write("y" * (1024 * 1024))
        sys.stderr.flush()

    if os.environ.get("AGENT_LOOP_MOCK_PARTIAL_HANG", "").strip() == "1":
        # Emit incomplete JSON then hang past the gate timeout.
        sys.stdout.write('{"verdict":"APPROVED","schema_version":"1.0"')
        sys.stdout.flush()
        import time

        time.sleep(3600)
        return 1

    refs = _parse_refs(instruction_text)
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
    body = json.dumps(payload, indent=2)
    out_msg = _output_last_message_path(argv)
    if out_msg:
        Path(out_msg).write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
