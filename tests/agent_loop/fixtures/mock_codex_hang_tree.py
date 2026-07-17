#!/usr/bin/env python3
"""Fake Codex that spawns a sleeping process tree for timeout kill tests.

Writes parent/child/grandchild PIDs to AGENT_LOOP_HANG_PID_FILE, then sleeps.
Used as AGENT_LOOP_CODEX_BIN — not a mock of Kill; the gate must reap the tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HELP_TEXT = """
Usage: codex exec [OPTIONS] <INSTRUCTION>

Options:
  --skip-git-repo-check
  --sandbox <MODE>           e.g. read-only
  --ignore-user-config
  --ignore-rules
  --ephemeral
  --output-last-message <FILE>
"""


def _append_pid(path: Path, pid: int) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{pid}\n")


def _spawn_tree(pid_file: Path) -> None:
    """Parent (this process) -> child sleeper -> grandchild sleeper."""
    pid_file.write_text("", encoding="utf-8")
    _append_pid(pid_file, os.getpid())

    # Grandchild: append PID then sleep.
    grand_code = (
        "import os,sys,time\n"
        "p=sys.argv[1]\n"
        "with open(p,'a',encoding='utf-8') as f: f.write(str(os.getpid())+'\\n')\n"
        "time.sleep(3600)\n"
    )
    # Child: append PID, spawn grandchild, sleep.
    child_code = (
        "import os,sys,time,subprocess\n"
        "p=sys.argv[1]\n"
        "with open(p,'a',encoding='utf-8') as f: f.write(str(os.getpid())+'\\n')\n"
        "subprocess.Popen([sys.executable,'-c',sys.argv[2],p])\n"
        "time.sleep(3600)\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", child_code, str(pid_file), grand_code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give children time to record PIDs before we hang.
    time.sleep(0.75)
    time.sleep(3600)


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "exec" and "--help" in argv:
        print(HELP_TEXT)
        return 0

    if not argv or argv[0] != "exec":
        print("mock_codex_hang_tree: expected 'exec' subcommand", file=sys.stderr)
        return 2

    pid_file = os.environ.get("AGENT_LOOP_HANG_PID_FILE", "").strip()
    if not pid_file:
        print(
            "mock_codex_hang_tree: AGENT_LOOP_HANG_PID_FILE required",
            file=sys.stderr,
        )
        return 2

    # Emit incomplete JSON so partial output must not become APPROVED.
    sys.stdout.write('{"verdict":"APPROVED","schema_version":"1.0"')
    sys.stdout.flush()
    _spawn_tree(Path(pid_file))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
